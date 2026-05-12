#!/usr/bin/env python3

import argparse
import difflib
import email.utils
import html
import json
import math
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta


RSS_URL_TEMPLATE = (
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
)
SEARCH_URL_TEMPLATE = (
    "https://news.google.com/search?q={query}&hl=en-US&gl=US&ceid=US:en"
)
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
OEMBED_ENDPOINTS = (
    "https://publish.x.com/oembed",
    "https://publish.twitter.com/oembed",
)
POST_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:x\.com|twitter\.com)/(?P<screen_name>[^/]+)/status/(?P<post_id>\d+)"
)
TRUNCATION_RE = re.compile(r"(?:…|\.{3})(?:\s+https?://t\.co/\S+)?\s*$")
SEARCH_RESULT_RE = re.compile(
    r'\[\[13,\[13,"[^"]+"\],"((?:\\.|[^"\\])*)",null,\[(\d+)\],null,'
    r'"(https://x\.com/[^"/]+/status/\d+)"'
)
TITLE_QUOTE_RE = re.compile(r'["“”]')
URLISH_TOKEN_RE = re.compile(r"(?:https?://\S+|\b\S+\.(?:com|net|org|io|ai|co|dev|fm|gg|ly)\S*)")
DEFAULT_SSL_CONTEXT = ssl.create_default_context()
INSECURE_SSL_CONTEXT = ssl._create_unverified_context()
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}


class ScrapeError(Exception):
    def __init__(self, label, message=None, status_code=None):
        super().__init__(message or label)
        self.label = label
        self.status_code = status_code


def canonical_handle(handle):
    return handle.lstrip("@")


def parse_retry_delays(raw_value):
    values = []
    for piece in raw_value.split(","):
        piece = piece.strip()
        if not piece:
            continue
        values.append(float(piece))
    return values or [2.0, 4.0, 8.0]


def parse_optional_float_list(raw_value):
    if raw_value is None:
        return []
    values = []
    for piece in raw_value.split(","):
        piece = piece.strip()
        if not piece:
            continue
        values.append(float(piece))
    return values


def fetch_text(url, *, method="GET", data=None, headers=None, retry_delays=None):
    retry_delays = retry_delays or [2.0, 4.0, 8.0]
    request_headers = dict(REQUEST_HEADERS)
    if headers:
        request_headers.update(headers)

    for attempt in range(len(retry_delays) + 1):
        try:
            with open_request(
                url,
                method=method,
                data=data,
                headers=request_headers,
                context=DEFAULT_SSL_CONTEXT,
            ) as response:
                body = response.read().decode("utf-8", errors="replace")
                return body, response.getcode()
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if not isinstance(reason, ssl.SSLCertVerificationError):
                raise
            with open_request(
                url,
                method=method,
                data=data,
                headers=request_headers,
                context=INSECURE_SSL_CONTEXT,
            ) as response:
                body = response.read().decode("utf-8", errors="replace")
                return body, response.getcode()
        except urllib.error.HTTPError as exc:
            if exc.code in RETRYABLE_HTTP_STATUS and attempt < len(retry_delays):
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else retry_delays[attempt]
                time.sleep(delay)
                continue
            raise


def open_request(url, *, method, data, headers, context):
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )
    return urllib.request.urlopen(request, timeout=30, context=context)


def parse_pub_date(value):
    return email.utils.parsedate_to_datetime(value).astimezone()


def recency_days_for_hours(hours):
    return max(1, math.ceil(hours / 24))


def build_rss_query(handle, hours):
    days = recency_days_for_hours(hours)
    return f"site:x.com/{handle} when:{days}d"


def build_rss_url(handle, hours):
    query = urllib.parse.quote(build_rss_query(handle, hours))
    return RSS_URL_TEMPLATE.format(query=query)


def build_search_url(query):
    return SEARCH_URL_TEMPLATE.format(query=urllib.parse.quote(query))


def parse_rss_items(xml_text):
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall("./channel/item"):
        items.append(
            {
                "rss_title": (item.findtext("title") or "").strip(),
                "google_news_url": (item.findtext("link") or "").strip(),
                "rss_guid": (item.findtext("guid") or "").strip(),
                "rss_pub_date": (item.findtext("pubDate") or "").strip(),
            }
        )
    return items


def clean_rss_title(rss_title):
    title = (rss_title or "").strip()
    if title.endswith(" - x.com"):
        title = title[:-8].strip()
    return re.sub(r"\s+", " ", title)


def normalize_title_for_matching(text):
    text = clean_rss_title(text)
    text = TITLE_QUOTE_RE.sub(" ", text)
    text = URLISH_TOKEN_RE.sub(" ", text)
    text = re.sub(r"[^0-9A-Za-z@#'’\-\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def build_search_queries(handle, rss_title):
    cleaned = clean_rss_title(rss_title)
    normalized = TITLE_QUOTE_RE.sub(" ", cleaned)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    without_urlish = re.sub(r"\s+", " ", URLISH_TOKEN_RE.sub(" ", normalized)).strip()

    candidates = []
    for piece in (normalized, without_urlish):
        if not piece:
            continue
        candidates.append(piece)
        if len(piece) > 120:
            candidates.append(piece[:120].rsplit(" ", 1)[0].strip() or piece[:120].strip())

    seen = set()
    queries = []
    for piece in candidates:
        if not piece:
            continue
        query = f'"{piece}" site:x.com/{handle}'
        if query in seen:
            continue
        seen.add(query)
        queries.append(query)
    return queries


def parse_search_page_candidates(text, handle):
    candidates = []
    seen_urls = set()
    lowered_handle = handle.lower()

    for match in SEARCH_RESULT_RE.finditer(text):
        title = json.loads(f'"{match.group(1)}"')
        url = match.group(3)
        normalized = normalize_post_url(url)
        if not normalized:
            continue
        if normalized["screen_name"].lower() != lowered_handle:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        candidates.append(
            {
                "result_title": title,
                "post_url": normalized["post_url"],
                "post_id": normalized["post_id"],
                "screen_name": normalized["screen_name"],
                "result_timestamp": int(match.group(2)),
            }
        )

    return candidates


def score_search_candidate(rss_title, candidate):
    target = normalize_title_for_matching(rss_title)
    result = normalize_title_for_matching(candidate["result_title"])
    if not target or not result:
        return 0.0

    ratio = difflib.SequenceMatcher(a=target, b=result).ratio()
    target_tokens = set(target.split())
    result_tokens = set(result.split())
    overlap = len(target_tokens & result_tokens) / max(1, len(target_tokens))
    prefix_bonus = 1.0 if result.startswith(target[: min(len(target), 32)]) else 0.0
    return ratio + overlap + prefix_bonus


def search_post_url_via_google_news(handle, rss_title, retry_delays):
    queries = build_search_queries(handle, rss_title)
    last_retryable_error = None

    for query in queries:
        search_url = build_search_url(query)
        try:
            text, _status = fetch_text(search_url, retry_delays=retry_delays)
        except urllib.error.HTTPError as exc:
            last_retryable_error = ScrapeError(
                f"google_news_search_http_{exc.code}",
                f"Google News search page returned HTTP {exc.code}",
                status_code=exc.code,
            )
            if exc.code in RETRYABLE_HTTP_STATUS:
                continue
            raise last_retryable_error from exc

        candidates = parse_search_page_candidates(text, handle)
        if not candidates:
            continue

        best_candidate = max(candidates, key=lambda candidate: score_search_candidate(rss_title, candidate))
        return {
            "query": query,
            "candidates": candidates,
            "best_candidate": best_candidate,
        }

    if last_retryable_error:
        raise last_retryable_error
    return None


def fetch_rss_items(handle, retry_delays, hours):
    rss_url = build_rss_url(handle, hours)
    try:
        rss_text, _status = fetch_text(rss_url, retry_delays=retry_delays)
    except urllib.error.HTTPError as exc:
        raise ScrapeError(
            f"google_news_rss_http_{exc.code}",
            f"Google News RSS returned HTTP {exc.code}",
            status_code=exc.code,
        ) from exc
    return parse_rss_items(rss_text)


def extract_google_news_id(google_news_url):
    parsed = urllib.parse.urlparse(google_news_url)
    parts = [part for part in parsed.path.split("/") if part]
    return parts[-1] if parts else None


def get_decode_signals(article_id, retry_delays):
    article_url = f"https://news.google.com/articles/{article_id}"
    try:
        text, _status = fetch_text(article_url, retry_delays=retry_delays)
    except urllib.error.HTTPError as exc:
        raise ScrapeError(
            f"google_news_decode_http_{exc.code}",
            f"Google News article page returned HTTP {exc.code}",
            status_code=exc.code,
        ) from exc

    ts_match = re.search(r'data-n-a-ts="([^"]+)"', text)
    sg_match = re.search(r'data-n-a-sg="([^"]+)"', text)
    if not ts_match or not sg_match:
        raise ScrapeError(
            "google_news_decode_missing_signals",
            "Missing Google News decode signals",
        )

    return {
        "article_id": article_id,
        "timestamp": int(ts_match.group(1)),
        "signature": sg_match.group(1),
    }


def parse_batchexecute_response(text):
    escaped_match = re.search(r'\[\\"garturlres\\",\\"(.*?)\\",', text)
    if escaped_match:
        return json.loads(f'"{escaped_match.group(1)}"')

    plain_match = re.search(r'\["garturlres","(.*?)",', text)
    if plain_match:
        return json.loads(f'"{plain_match.group(1)}"')

    raise ScrapeError(
        "google_news_decode_unparsed_response",
        "Could not parse decoded URL from batchexecute response",
    )


def decode_google_news_url(google_news_url, retry_delays):
    article_id = extract_google_news_id(google_news_url)
    if not article_id:
        raise ScrapeError("google_news_decode_missing_article_id", "Missing article id")

    signals = get_decode_signals(article_id, retry_delays)
    request_payload = [
        "garturlreq",
        [
            [
                "X",
                "X",
                ["X", "X"],
                None,
                None,
                1,
                1,
                "US:en",
                None,
                1,
                None,
                None,
                None,
                None,
                None,
                0,
                1,
            ],
            "X",
            "X",
            1,
            [1, 1, 1],
            1,
            1,
            None,
            0,
            0,
            None,
            0,
        ],
        signals["article_id"],
        signals["timestamp"],
        signals["signature"],
    ]
    f_req = json.dumps([[["Fbv4je", json.dumps(request_payload)]]], separators=(",", ":"))
    body = urllib.parse.urlencode({"f.req": f_req}).encode("utf-8")

    try:
        response_text, _status = fetch_text(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
            method="POST",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            retry_delays=retry_delays,
        )
    except urllib.error.HTTPError as exc:
        raise ScrapeError(
            f"google_news_decode_http_{exc.code}",
            f"Google News batchexecute returned HTTP {exc.code}",
            status_code=exc.code,
        ) from exc

    decoded_url = parse_batchexecute_response(response_text)
    return decoded_url, signals


def normalize_post_url(decoded_url):
    match = POST_URL_RE.search(decoded_url)
    if not match:
        return None
    return {
        "post_url": f"https://x.com/{match.group('screen_name')}/status/{match.group('post_id')}",
        "screen_name": match.group("screen_name"),
        "post_id": match.group("post_id"),
    }


def extract_text_from_oembed_html(oembed_html):
    paragraph_match = re.search(r"<p\b[^>]*>(.*?)</p>", oembed_html, re.DOTALL | re.IGNORECASE)
    if not paragraph_match:
        return ""
    text = paragraph_match.group(1)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<a\b[^>]*>(.*?)</a>", r"\1", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+\n", "\n", text).strip()


def is_text_truncated(text):
    return bool(TRUNCATION_RE.search(text))


def fetch_oembed(post_url, retry_delays):
    last_error = None

    for endpoint in OEMBED_ENDPOINTS:
        query = urllib.parse.urlencode({"url": post_url, "omit_script": "1"})
        url = f"{endpoint}?{query}"
        try:
            text, status_code = fetch_text(url, retry_delays=retry_delays)
            payload = json.loads(text)
            payload["_endpoint"] = endpoint
            return payload, status_code
        except urllib.error.HTTPError as exc:
            last_error = ScrapeError(
                f"oembed_http_{exc.code}",
                f"oEmbed endpoint returned HTTP {exc.code}",
                status_code=exc.code,
            )
        except json.JSONDecodeError as exc:
            last_error = ScrapeError("oembed_invalid_json", str(exc))

    if last_error:
        raise last_error
    raise ScrapeError("oembed_failed", "Unknown oEmbed failure")


def build_empty_summary():
    return {
        "rss_items_total": 0,
        "candidates_in_window": 0,
        "rows_emitted": 0,
        "text_extracted": 0,
        "full_text_confident": 0,
        "truncated": 0,
        "failed": 0,
        "rate_limited": 0,
        "no_candidates": False,
        "decode_retries_performed": 0,
        "recovered_after_retry": 0,
    }


def is_rate_limit_label(label):
    return label.endswith("_429")


def is_retryable_decode_error(exc):
    return (
        (
            exc.label.startswith("google_news_decode_http_")
            or exc.label.startswith("google_news_search_http_")
        )
        and exc.status_code in RETRYABLE_HTTP_STATUS
    )


def build_candidate_row(handle, item, now, debug, discovery_query):
    row = {
        "query": f"site:x.com/{handle}",
        "discovery_query": discovery_query,
        "discovery_source": "google_news_rss",
        "rss_title": item["rss_title"],
        "rss_pub_date": item["_pub_dt"].isoformat(),
        "google_news_url": item["google_news_url"],
        "decoded_source_url": None,
        "post_url": None,
        "post_id": None,
        "screen_name": None,
        "author_name": None,
        "author_url": None,
        "text": None,
        "text_length": 0,
        "is_truncated": False,
        "full_text_confident": False,
        "extraction_status": "failed",
        "oembed_status_code": None,
        "oembed_endpoint": None,
        "failure_reason": None,
        "collected_at": now.isoformat(),
        "decode_attempts": 0,
        "url_restore_method": None,
    }
    if debug:
        row["debug"] = {}
    return row


def finalize_failed_row(row, summary, exc):
    row["failure_reason"] = exc.label
    if exc.status_code is not None and exc.label.startswith("oembed_"):
        row["oembed_status_code"] = exc.status_code
    summary["failed"] += 1
    if is_rate_limit_label(exc.label):
        summary["rate_limited"] += 1
    summary["rows_emitted"] += 1
    return row


def process_candidate_attempt(
    *,
    row,
    item,
    seen_post_ids,
    retry_delays,
    debug,
    summary,
):
    row["decode_attempts"] += 1
    decode_retry_delays = []

    try:
        decoded_source_url, signals = decode_google_news_url(item["google_news_url"], decode_retry_delays)
        row["decoded_source_url"] = decoded_source_url
        row["url_restore_method"] = "google_news_batchexecute"
        if debug:
            row["debug"]["google_news_signals"] = signals
        normalized = normalize_post_url(decoded_source_url)
        if not normalized:
            raise ScrapeError("decoded_url_not_x_status", "Decoded URL is not an X status URL")
        row.update(normalized)
        if row["post_id"] in seen_post_ids:
            return "duplicate", None
        seen_post_ids.add(row["post_id"])
    except ScrapeError as exc:
        try:
            fallback = search_post_url_via_google_news(
                handle=canonical_handle(row["query"].rsplit("/", 1)[-1]),
                rss_title=item["rss_title"],
                retry_delays=retry_delays,
            )
        except ScrapeError as fallback_exc:
            if debug:
                row["debug"]["google_news_search_fallback_error"] = fallback_exc.label
                row["debug"]["google_news_primary_decode_error"] = exc.label
            return "decode_error", fallback_exc

        if not fallback:
            if debug:
                row["debug"]["google_news_primary_decode_error"] = exc.label
                row["debug"]["google_news_search_fallback_error"] = "google_news_search_no_match"
            return "decode_error", exc

        best_candidate = fallback["best_candidate"]
        row["decoded_source_url"] = best_candidate["post_url"]
        row["url_restore_method"] = "google_news_search"
        if debug:
            row["debug"]["google_news_primary_decode_error"] = exc.label
            row["debug"]["google_news_search_fallback"] = fallback
        normalized = normalize_post_url(best_candidate["post_url"])
        if not normalized:
            return "decode_error", ScrapeError(
                "search_decoded_url_not_x_status",
                "Search fallback produced a non-status URL",
            )
        row.update(normalized)
        if row["post_id"] in seen_post_ids:
            return "duplicate", None
        seen_post_ids.add(row["post_id"])
    except Exception:
        return "unexpected_error", ScrapeError("unexpected_error", "Unexpected decode error")

    try:
        payload, status_code = fetch_oembed(row["post_url"], retry_delays)
        row["oembed_status_code"] = status_code
        row["oembed_endpoint"] = payload.get("_endpoint")
        row["author_name"] = payload.get("author_name")
        row["author_url"] = payload.get("author_url")
        text = extract_text_from_oembed_html(payload.get("html", ""))
        if not text:
            raise ScrapeError("oembed_text_empty", "oEmbed HTML did not contain visible text")
        row["text"] = text
        row["text_length"] = len(text)
        row["is_truncated"] = is_text_truncated(text)
        row["full_text_confident"] = not row["is_truncated"]
        row["extraction_status"] = "text_extracted"
        summary["text_extracted"] += 1
        if row["full_text_confident"]:
            summary["full_text_confident"] += 1
        if row["is_truncated"]:
            summary["truncated"] += 1
        summary["rows_emitted"] += 1
        if row["decode_attempts"] > 1:
            summary["recovered_after_retry"] += 1
        return "success", None
    except ScrapeError as exc:
        finalize_failed_row(row, summary, exc)
        return "final_failure", exc
    except Exception:
        exc = ScrapeError("unexpected_error", "Unexpected oEmbed error")
        finalize_failed_row(row, summary, exc)
        return "final_failure", exc


def scrape_handle(
    handle,
    *,
    hours,
    now,
    limit_per_handle,
    retry_delays,
    row_throttle_seconds,
    decode_retry_cooldowns,
    debug,
):
    handle = canonical_handle(handle)
    cutoff = now - timedelta(hours=hours)
    rows = []
    summary = build_empty_summary()
    seen_post_ids = set()

    try:
        discovery_query = build_rss_query(handle, hours)
        items = fetch_rss_items(handle, retry_delays, hours)
    except ScrapeError as exc:
        summary["failed"] += 1
        if is_rate_limit_label(exc.label):
            summary["rate_limited"] += 1
        return rows, summary, exc.label

    summary["rss_items_total"] = len(items)
    candidates = []
    for item in items:
        try:
            pub_dt = parse_pub_date(item["rss_pub_date"])
        except Exception:
            continue
        if pub_dt >= cutoff:
            item["_pub_dt"] = pub_dt
            candidates.append(item)

    summary["candidates_in_window"] = len(candidates)
    if not candidates:
        summary["no_candidates"] = True
        return rows, summary, None

    if limit_per_handle is not None:
        candidates = candidates[:limit_per_handle]

    pending_states = [
        {
            "item": item,
            "row": build_candidate_row(handle, item, now, debug, discovery_query),
        }
        for item in candidates
    ]

    max_decode_attempts = 1 + len(decode_retry_cooldowns)
    round_index = 0
    while pending_states:
        if round_index > 0:
            time.sleep(decode_retry_cooldowns[round_index - 1])

        next_pending_states = []
        for state in pending_states:
            row = state["row"]
            item = state["item"]
            status, exc = process_candidate_attempt(
                row=row,
                item=item,
                seen_post_ids=seen_post_ids,
                retry_delays=retry_delays,
                debug=debug,
                summary=summary,
            )

            if status == "success":
                rows.append(row)
            elif status == "duplicate":
                pass
            elif status == "decode_error":
                if is_retryable_decode_error(exc) and row["decode_attempts"] < max_decode_attempts:
                    summary["decode_retries_performed"] += 1
                    next_pending_states.append(state)
                else:
                    finalize_failed_row(row, summary, exc)
                    rows.append(row)
            else:
                rows.append(row)

            time.sleep(row_throttle_seconds)

        pending_states = next_pending_states
        round_index += 1

    return rows, summary, None


def main():
    parser = argparse.ArgumentParser(
        description="Discover recent public X posts through Google News and extract text via oEmbed.",
    )
    parser.add_argument("handles", nargs="+", help="Handles like @OpenAI or OpenAI")
    parser.add_argument("--hours", type=int, default=48, help="Lookback window in hours")
    parser.add_argument(
        "--limit-per-handle",
        type=int,
        default=None,
        help="Maximum candidate rows to process per handle",
    )
    parser.add_argument(
        "--row-throttle-seconds",
        type=float,
        default=0.35,
        help="Pause between candidate rows to reduce rate limiting",
    )
    parser.add_argument(
        "--retry-delays",
        default="2,4,8",
        help="Comma-separated retry delays in seconds for retryable HTTP errors",
    )
    parser.add_argument(
        "--decode-retry-cooldowns",
        default="15",
        help="Comma-separated cool-down delays in seconds for deferred Google News decode retries after rate limiting",
    )
    parser.add_argument("--output", help="Write JSON output to this file")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Include intermediate debug fields such as Google News decode signals",
    )
    args = parser.parse_args()

    now = datetime.now().astimezone()
    retry_delays = parse_retry_delays(args.retry_delays)
    decode_retry_cooldowns = parse_optional_float_list(args.decode_retry_cooldowns)
    handles = [canonical_handle(handle) for handle in args.handles]
    summary = {handle: build_empty_summary() for handle in handles}
    rows = []
    handle_errors = {}

    for handle in handles:
        handle_rows, handle_summary, handle_error = scrape_handle(
            handle,
            hours=args.hours,
            now=now,
            limit_per_handle=args.limit_per_handle,
            retry_delays=retry_delays,
            row_throttle_seconds=args.row_throttle_seconds,
            decode_retry_cooldowns=decode_retry_cooldowns,
            debug=args.debug,
        )
        summary[handle] = handle_summary
        if handle_error:
            handle_errors[handle] = handle_error
        rows.extend(handle_rows)

    result = {
        "lookback_hours": args.hours,
        "generated_at": now.isoformat(),
        "handles": handles,
        "summary": summary,
        "rows": rows,
    }
    if handle_errors:
        result["handle_errors"] = handle_errors

    output_text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output_text)
            fh.write("\n")
    print(output_text)


if __name__ == "__main__":
    main()
