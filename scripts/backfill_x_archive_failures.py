#!/usr/bin/env python3

import argparse
import importlib.util
import json
import time
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path


DISCOVER_SCRIPT = Path(__file__).resolve().with_name("discover_public_x_posts.py")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_discover_module():
    spec = importlib.util.spec_from_file_location("discover_public_x_posts", DISCOVER_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_pub_date(value):
    if not value:
        return datetime.fromtimestamp(0).astimezone()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value)
    except Exception:
        return datetime.fromtimestamp(0).astimezone()


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_cache_entry(row, generated_at):
    return {
        "cached_from_generated_at": generated_at,
        "google_news_url": row.get("google_news_url"),
        "decoded_source_url": row.get("decoded_source_url"),
        "post_url": row.get("post_url"),
        "post_id": row.get("post_id"),
        "screen_name": row.get("screen_name"),
        "author_name": row.get("author_name"),
        "author_url": row.get("author_url"),
        "text": row.get("text"),
        "text_length": row.get("text_length", 0),
        "is_truncated": row.get("is_truncated", False),
        "full_text_confident": row.get("full_text_confident", False),
        "extraction_status": row.get("extraction_status"),
        "oembed_status_code": row.get("oembed_status_code"),
        "oembed_endpoint": row.get("oembed_endpoint"),
    }


def select_retry_candidates(rows, limit, min_age_minutes):
    now = datetime.now().astimezone()
    cutoff = now - timedelta(minutes=min_age_minutes)
    candidates = [
        row for row in rows
        if row.get("extraction_status") != "text_extracted"
        and row.get("failure_reason") == "google_news_decode_http_429"
        and row.get("google_news_url")
        and (
            parse_iso_datetime(row.get("last_seen_at")) is None
            or parse_iso_datetime(row.get("last_seen_at")) <= cutoff
        )
    ]
    candidates.sort(key=lambda row: parse_pub_date(row.get("rss_pub_date")), reverse=True)
    return candidates[:limit]


def retry_row(row, mod, retry_delays, now_iso):
    row["archive_backfill_attempts"] = int(row.get("archive_backfill_attempts", 0)) + 1
    row["last_archive_backfill_retry_at"] = now_iso

    try:
        decoded_url, _signals = mod.decode_google_news_url(row["google_news_url"], retry_delays)
        normalized = mod.normalize_post_url(decoded_url)
        if not normalized:
            raise mod.ScrapeError("decoded_url_not_x_status", "Decoded URL is not an X status URL")

        payload, status_code = mod.fetch_oembed(normalized["post_url"], retry_delays)
        text = mod.extract_text_from_oembed_html(payload.get("html", ""))
        if not text:
            raise mod.ScrapeError("oembed_text_empty", "oEmbed HTML did not contain visible text")

        row.update(normalized)
        row["decoded_source_url"] = decoded_url
        row["author_name"] = payload.get("author_name")
        row["author_url"] = payload.get("author_url")
        row["text"] = text
        row["text_length"] = len(text)
        row["is_truncated"] = mod.is_text_truncated(text)
        row["full_text_confident"] = not row["is_truncated"]
        row["extraction_status"] = "text_extracted"
        row["oembed_status_code"] = status_code
        row["oembed_endpoint"] = payload.get("_endpoint")
        row["failure_reason"] = None
        row["backfilled_from_archive_retry"] = True
        row["archive_backfill_recovered_at"] = now_iso
        return True, None
    except Exception as exc:
        row["failure_reason"] = getattr(exc, "label", str(exc))
        if getattr(exc, "status_code", None) is not None and str(row["failure_reason"]).startswith("oembed_"):
            row["oembed_status_code"] = exc.status_code
        row["backfilled_from_archive_retry"] = False
        return False, getattr(exc, "label", str(exc))


def main():
    parser = argparse.ArgumentParser(description="Retry archived unresolved X rows and backfill recovered posts.")
    parser.add_argument("archive_json")
    parser.add_argument("decode_cache_json")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--min-age-minutes", type=int, default=60)
    parser.add_argument("--row-throttle-seconds", type=float, default=1.0)
    parser.add_argument("--retry-delays", default="3,8,20,45")
    args = parser.parse_args()

    archive = load_json(args.archive_json)
    decode_cache = load_json(args.decode_cache_json)
    mod = load_discover_module()
    retry_delays = mod.parse_retry_delays(args.retry_delays)
    now_iso = datetime.now().astimezone().isoformat()

    rows = archive.get("rows", [])
    selected = select_retry_candidates(rows, args.limit, args.min_age_minutes)
    attempted = 0
    recovered = 0
    recovered_handles = {}

    for row in selected:
        attempted += 1
        success, error = retry_row(row, mod, retry_delays, now_iso)
        if success:
            recovered += 1
            handle = row.get("screen_name") or row.get("query", "").rsplit("/", 1)[-1]
            recovered_handles.setdefault(handle, 0)
            recovered_handles[handle] += 1
            decode_cache.setdefault("entries", {})[row["google_news_url"]] = build_cache_entry(row, now_iso)
        time.sleep(args.row_throttle_seconds)

    archive["generated_at"] = now_iso
    archive["backfill_stats"] = {
        "attempted": attempted,
        "recovered": recovered,
        "remaining_failed": sum(1 for row in rows if row.get("extraction_status") != "text_extracted"),
    }
    decode_cache["generated_at"] = now_iso

    write_json(args.archive_json, archive)
    write_json(args.decode_cache_json, decode_cache)

    print(json.dumps(
        {
            "archive_json": args.archive_json,
            "decode_cache_json": args.decode_cache_json,
            "attempted": attempted,
            "recovered": recovered,
            "remaining_failed": archive["backfill_stats"]["remaining_failed"],
            "min_age_minutes": args.min_age_minutes,
            "recovered_handles": recovered_handles,
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
