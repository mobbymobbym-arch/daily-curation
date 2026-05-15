#!/usr/bin/env python3

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import discover_public_x_posts as discover_module


ROOT = Path(__file__).resolve().parents[1]
DISCOVER_SCRIPT = ROOT / "scripts/discover_public_x_posts.py"
RENDER_SCRIPT = ROOT / "scripts/render_daily_curation_x_tab_preview.py"
TRANSLATE_SCRIPT = ROOT / "scripts/translate_x_watch_archive.py"
BACKFILL_SCRIPT = ROOT / "scripts/backfill_x_archive_failures.py"
HANDLES_CONFIG = ROOT / "config/x_watch_handles.json"
WORKFLOW_CONFIG = ROOT / "config/x_watch_workflow.json"
WORKFLOW_SECRETS_CONFIG = ROOT / "config/x_watch_secrets.local.json"
REPORTS_DIR = ROOT / "reports"
PREVIEW_PATH = ROOT / "daily_curation_x_tab_preview.html"
DECODE_CACHE_PATH = REPORTS_DIR / "x_watch_decode_cache.json"
ARCHIVE_PATH = REPORTS_DIR / "x_watch_archive_latest.json"
SITE_X_POSTS_PATH = Path.home() / "daily-curation" / "x-posts.html"
SITE_REPO_PATH = SITE_X_POSTS_PATH.parent
SITE_X_POSTS_RELATIVE_PATH = SITE_X_POSTS_PATH.name
SITE_PUBLISH_URL = "https://mobbymobbym-arch.github.io/daily-curation/x-posts.html"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def chunked(values, size):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def workflow_positive_int(workflow, key, default):
    value = int(workflow.get(key, default))
    if value < 1:
        raise ValueError(f"{key} must be at least 1")
    return value


def load_workflow_secrets(path=WORKFLOW_SECRETS_CONFIG):
    if not path.exists():
        return {}
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"workflow secrets payload must be an object: {path}")
    return payload


def build_translate_env():
    env = dict(os.environ)
    env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
    return env


def run_parallel_preserve_order(items, max_workers, worker):
    if not items:
        return []

    if max_workers <= 1:
        return [worker(item) for item in items]

    results = [None] * len(items)
    worker_count = min(max_workers, len(items))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_index = {
            executor.submit(worker, item): index
            for index, item in enumerate(items)
        }
        for future in as_completed(future_to_index):
            results[future_to_index[future]] = future.result()

    return results


def run_discover(handles, *, hours, row_throttle_seconds, retry_delays, decode_retry_cooldowns, output_path):
    command = [
        sys.executable,
        str(DISCOVER_SCRIPT),
        *[f"@{handle}" for handle in handles],
        "--hours",
        str(hours),
        "--row-throttle-seconds",
        str(row_throttle_seconds),
        "--retry-delays",
        retry_delays,
        "--decode-retry-cooldowns",
        decode_retry_cooldowns,
        "--output",
        str(output_path),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        if not details:
            details = str(exc)
        raise RuntimeError(f"discover failed for {', '.join(handles)}: {details}") from exc
    return load_json(output_path)


def synthesize_handle_result(handle, *, hours, summary, generated_at, error=None):
    result = {
        "lookback_hours": hours,
        "generated_at": generated_at,
        "handles": [handle],
        "summary": {handle: summary},
        "rows": [],
    }
    if error:
        result["handle_errors"] = {handle: error}
    return result


def merge_result_sets(handles, result_sets):
    merged_summary = {}
    merged_rows = []
    merged_handle_errors = {}

    for result in result_sets:
        merged_summary.update(result.get("summary", {}))
        merged_rows.extend(result.get("rows", []))
        merged_handle_errors.update(result.get("handle_errors", {}))

    merged = {
        "lookback_hours": result_sets[0]["lookback_hours"] if result_sets else None,
        "generated_at": datetime.now().astimezone().isoformat(),
        "handles": handles,
        "summary": merged_summary,
        "rows": merged_rows,
    }
    if merged_handle_errors:
        merged["handle_errors"] = merged_handle_errors
    return merged


def preflight_handle(handle, *, hours, now, retry_delays):
    handle = discover_module.canonical_handle(handle)
    summary = discover_module.build_empty_summary()
    cutoff = now - timedelta(hours=hours)

    try:
        items = discover_module.fetch_rss_items(handle, retry_delays, hours)
    except discover_module.ScrapeError as exc:
        summary["failed"] += 1
        if discover_module.is_rate_limit_label(exc.label):
            summary["rate_limited"] += 1
        return {
            "handle": handle,
            "summary": summary,
            "handle_error": exc.label,
            "candidate_count": 0,
            "latest_candidate_at": None,
        }

    summary["rss_items_total"] = len(items)
    latest_candidate_at = None
    candidate_count = 0
    for item in items:
        try:
            pub_dt = discover_module.parse_pub_date(item["rss_pub_date"])
        except Exception:
            continue
        if pub_dt >= cutoff:
            candidate_count += 1
            if latest_candidate_at is None or pub_dt > latest_candidate_at:
                latest_candidate_at = pub_dt

    summary["candidates_in_window"] = candidate_count
    summary["no_candidates"] = candidate_count == 0
    return {
        "handle": handle,
        "summary": summary,
        "handle_error": None,
        "candidate_count": candidate_count,
        "latest_candidate_at": latest_candidate_at,
    }


def select_primary_profile(candidate_count, workflow):
    if candidate_count > workflow["high_candidate_threshold"]:
        return {
            "row_throttle_seconds": workflow["high_row_throttle_seconds"],
            "retry_delays": workflow["high_retry_delays"],
            "decode_retry_cooldowns": workflow["high_decode_retry_cooldowns"],
            "sleep_after_handle_seconds": workflow["sleep_after_high_volume_handle_seconds"],
        }

    if candidate_count > workflow["medium_candidate_threshold"]:
        return {
            "row_throttle_seconds": workflow["medium_row_throttle_seconds"],
            "retry_delays": workflow["medium_retry_delays"],
            "decode_retry_cooldowns": workflow["medium_decode_retry_cooldowns"],
            "sleep_after_handle_seconds": workflow["sleep_between_handles_seconds"],
        }

    return {
        "row_throttle_seconds": workflow["primary_row_throttle_seconds"],
        "retry_delays": workflow["primary_retry_delays"],
        "decode_retry_cooldowns": workflow["primary_decode_retry_cooldowns"],
        "sleep_after_handle_seconds": workflow["sleep_between_handles_seconds"],
    }


def run_preflight_parallel(handles, *, hours, now, retry_delays, concurrency):
    return run_parallel_preserve_order(
        handles,
        concurrency,
        lambda handle: preflight_handle(handle, hours=hours, now=now, retry_delays=retry_delays),
    )


def run_primary_parallel(infos, *, hours, workflow, run_dir, concurrency):
    def worker(info):
        profile = select_primary_profile(info["candidate_count"], workflow)
        output_path = run_dir / f"primary_{info['handle']}.json"
        result = run_discover(
            [info["handle"]],
            hours=hours,
            row_throttle_seconds=profile["row_throttle_seconds"],
            retry_delays=profile["retry_delays"],
            decode_retry_cooldowns=profile["decode_retry_cooldowns"],
            output_path=output_path,
        )
        return info["handle"], result

    return dict(run_parallel_preserve_order(infos, concurrency, worker))


def run_rerun_like_parallel(handles, *, hours, workflow, run_dir, stage, concurrency):
    def worker(handle):
        output_path = run_dir / f"{stage}_{handle}.json"
        result = run_discover(
            [handle],
            hours=hours,
            row_throttle_seconds=workflow["rerun_row_throttle_seconds"],
            retry_delays=workflow["rerun_retry_delays"],
            decode_retry_cooldowns=workflow["rerun_decode_retry_cooldowns"],
            output_path=output_path,
        )
        return handle, result

    return dict(run_parallel_preserve_order(handles, concurrency, worker))


def should_rescue_before_high(summary):
    return (
        summary["candidates_in_window"] > 0
        and summary["text_extracted"] == 0
        and summary["rate_limited"] == summary["failed"]
        and summary["rate_limited"] > 0
    )


def handle_for_row(row):
    query = row.get("query", "")
    if "/" in query:
        return query.rsplit("/", 1)[-1]
    return query.lstrip("@")


def row_identity_candidates(row):
    candidates = []
    if row.get("google_news_url"):
        candidates.append(("google_news_url", row["google_news_url"]))
    if row.get("post_url"):
        candidates.append(("post_url", row["post_url"]))
    if row.get("post_id"):
        candidates.append(("post_id", str(row["post_id"])))
    return candidates


def row_quality_score(row):
    score = 0
    if row.get("extraction_status") == "text_extracted":
        score += 1000
    if row.get("post_url"):
        score += 100
    if row.get("full_text_confident"):
        score += 50
    if row.get("text"):
        score += min(len(row["text"]), 400)
    if row.get("is_truncated"):
        score -= 20
    return score


def build_archive_entry(row, seen_at):
    entry = dict(row)
    entry["archive_key"] = row.get("post_url") or row.get("google_news_url")
    entry["first_seen_at"] = seen_at
    entry["last_seen_at"] = seen_at
    entry["last_seen_in_run_at"] = seen_at
    entry["seen_count"] = 1
    return entry


def merge_archive_row(existing, incoming, seen_at):
    existing_score = row_quality_score(existing)
    incoming_score = row_quality_score(incoming)
    if incoming_score >= existing_score:
        merged = dict(existing)
        merged.update(incoming)
        updated = True
    else:
        merged = dict(existing)
        updated = False

    merged["archive_key"] = (
        existing.get("archive_key")
        or incoming.get("post_url")
        or incoming.get("google_news_url")
        or existing.get("post_url")
        or existing.get("google_news_url")
    )
    merged["first_seen_at"] = existing.get("first_seen_at", seen_at)
    merged["last_seen_at"] = seen_at
    merged["last_seen_in_run_at"] = seen_at
    merged["seen_count"] = int(existing.get("seen_count", 1)) + 1
    return merged, updated


def load_archive():
    if ARCHIVE_PATH.exists():
        return load_json(ARCHIVE_PATH)

    seeded_rows = []
    seed_stats = {"new_rows_added": 0, "rows_upgraded": 0, "rows_seen_again": 0}
    for path in sorted(REPORTS_DIR.glob("x_watch_results_*.json"), key=lambda item: item.stat().st_mtime):
        payload = load_json(path)
        seeded_rows, step_stats = merge_rows_into_archive(
            seeded_rows,
            payload.get("rows", []),
            payload.get("generated_at") or datetime.now().astimezone().isoformat(),
        )
        for key, value in step_stats.items():
            seed_stats[key] += value

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "rows": seeded_rows,
        "stats": seed_stats,
    }


def merge_rows_into_archive(existing_rows, incoming_rows, seen_at):
    rows = [dict(row) for row in existing_rows]
    index = {}
    for idx, row in enumerate(rows):
        for key in row_identity_candidates(row):
            index[key] = idx

    stats = {"new_rows_added": 0, "rows_upgraded": 0, "rows_seen_again": 0}

    for incoming in incoming_rows:
        match_index = None
        for key in row_identity_candidates(incoming):
            if key in index:
                match_index = index[key]
                break

        if match_index is None:
            entry = build_archive_entry(incoming, seen_at)
            rows.append(entry)
            new_index = len(rows) - 1
            for key in row_identity_candidates(entry):
                index[key] = new_index
            stats["new_rows_added"] += 1
            continue

        merged_entry, updated = merge_archive_row(rows[match_index], incoming, seen_at)
        rows[match_index] = merged_entry
        for key in row_identity_candidates(merged_entry):
            index[key] = match_index
        if updated:
            stats["rows_upgraded"] += 1
        else:
            stats["rows_seen_again"] += 1

    return rows, stats


def update_archive(archive_payload, result):
    merged_rows, merge_stats = merge_rows_into_archive(
        archive_payload.get("rows", []),
        result.get("rows", []),
        result.get("generated_at") or datetime.now().astimezone().isoformat(),
    )
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "rows": merged_rows,
        "stats": merge_stats,
    }


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


def load_decode_cache():
    entries = {}

    if DECODE_CACHE_PATH.exists():
        payload = load_json(DECODE_CACHE_PATH)
        entries.update(payload.get("entries", {}))

    for path in sorted(REPORTS_DIR.glob("x_watch_results_*.json"), key=lambda item: item.stat().st_mtime):
        payload = load_json(path)
        for row in payload.get("rows", []):
            if row.get("extraction_status") != "text_extracted":
                continue
            google_news_url = row.get("google_news_url")
            if not google_news_url:
                continue
            entries[google_news_url] = build_cache_entry(row, payload.get("generated_at"))

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "entries": entries,
    }


def update_decode_cache(cache_payload, result):
    entries = dict(cache_payload.get("entries", {}))
    for row in result.get("rows", []):
        if row.get("extraction_status") != "text_extracted":
            continue
        google_news_url = row.get("google_news_url")
        if not google_news_url:
            continue
        entries[google_news_url] = build_cache_entry(row, result.get("generated_at"))

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "entries": entries,
    }


def apply_decode_cache(result, cache_payload):
    cache_hits = 0
    entries = cache_payload.get("entries", {})

    for row in result.get("rows", []):
        if row.get("extraction_status") == "text_extracted":
            continue

        google_news_url = row.get("google_news_url")
        if not google_news_url:
            continue

        cached = entries.get(google_news_url)
        if not cached or cached.get("extraction_status") != "text_extracted":
            continue

        handle = handle_for_row(row)
        summary = result["summary"][handle]

        if row.get("failure_reason"):
            summary["failed"] = max(0, summary["failed"] - 1)
            if str(row["failure_reason"]).endswith("_429"):
                summary["rate_limited"] = max(0, summary["rate_limited"] - 1)

        summary["text_extracted"] += 1
        if cached.get("full_text_confident"):
            summary["full_text_confident"] += 1
        if cached.get("is_truncated"):
            summary["truncated"] += 1

        row.update(
            {
                "decoded_source_url": cached.get("decoded_source_url"),
                "post_url": cached.get("post_url"),
                "post_id": cached.get("post_id"),
                "screen_name": cached.get("screen_name"),
                "author_name": cached.get("author_name"),
                "author_url": cached.get("author_url"),
                "text": cached.get("text"),
                "text_length": cached.get("text_length", 0),
                "is_truncated": cached.get("is_truncated", False),
                "full_text_confident": cached.get("full_text_confident", False),
                "extraction_status": "text_extracted",
                "oembed_status_code": cached.get("oembed_status_code"),
                "oembed_endpoint": cached.get("oembed_endpoint"),
                "failure_reason": None,
                "restored_from_cache": True,
                "cache_source_generated_at": cached.get("cached_from_generated_at"),
            }
        )
        cache_hits += 1

    return cache_hits


def score_handle_result(result, handle):
    summary = result["summary"][handle]
    return (
        summary["text_extracted"],
        summary["full_text_confident"],
        -summary["failed"],
        -summary["rate_limited"],
        -summary["truncated"],
    )


def replace_handle_result(base_result, replacement_result, handle):
    base_result["summary"][handle] = replacement_result["summary"][handle]
    base_rows = [row for row in base_result["rows"] if handle_for_row(row) != handle]
    replacement_rows = [row for row in replacement_result["rows"] if handle_for_row(row) == handle]
    base_result["rows"] = base_rows + replacement_rows
    if "handle_errors" in base_result and handle in base_result["handle_errors"]:
        del base_result["handle_errors"][handle]
        if not base_result["handle_errors"]:
            del base_result["handle_errors"]
    if replacement_result.get("handle_errors", {}).get(handle):
        base_result.setdefault("handle_errors", {})[handle] = replacement_result["handle_errors"][handle]


def load_known_translations():
    success = {}
    failed = {}
    for path in sorted(REPORTS_DIR.glob("x_post_translations*.json"), key=lambda item: item.stat().st_mtime):
        payload = load_json(path)
        success.update(payload.get("success_translations", {}))
        failed.update(payload.get("failed_candidate_translations", {}))
    x_watch_latest = REPORTS_DIR / "x_watch_translations_latest.json"
    if x_watch_latest.exists():
        payload = load_json(x_watch_latest)
        success.update(payload.get("success_translations", {}))
        failed.update(payload.get("failed_candidate_translations", {}))
    return {
        "success_translations": success,
        "failed_candidate_translations": failed,
    }


def build_missing_translation_scaffold(result, known_translations):
    missing_success = {}
    missing_failed = {}

    for row in result["rows"]:
        if row["extraction_status"] == "text_extracted":
            key = row["post_url"]
            if key and key not in known_translations["success_translations"]:
                missing_success[key] = ""
        else:
            key = row["google_news_url"]
            if key and key not in known_translations["failed_candidate_translations"]:
                missing_failed[key] = ""

    return {
        "success_translations": missing_success,
        "failed_candidate_translations": missing_failed,
    }


def list_rate_limited_handles(result):
    return [handle for handle, summary in result["summary"].items() if summary["rate_limited"] > 0]


def list_no_candidate_handles(result):
    return [handle for handle, summary in result["summary"].items() if summary["no_candidates"]]


def render_preview(result_path, translation_path):
    command = [
        sys.executable,
        str(RENDER_SCRIPT),
        str(result_path),
        str(translation_path),
        "--output",
        str(PREVIEW_PATH),
    ]
    subprocess.run(command, check=True)


def completed_process_details(completed):
    details = {"returncode": completed.returncode}
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if stdout:
        details["stdout"] = stdout[-2000:]
    if stderr:
        details["stderr"] = stderr[-2000:]
    return details


def run_site_git(args):
    return subprocess.run(
        ["git", "-C", str(SITE_REPO_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def porcelain_path(line):
    if " -> " in line:
        return line.rsplit(" -> ", 1)[-1].strip()
    return line[3:].strip()


def inspect_site_worktree():
    completed = run_site_git(["status", "--porcelain"])
    if completed.returncode != 0:
        return None, {
            "status": "failed_git_status",
            **completed_process_details(completed),
        }

    changes = [line for line in completed.stdout.splitlines() if line.strip()]
    x_posts_changes = [
        line
        for line in changes
        if porcelain_path(line) == SITE_X_POSTS_RELATIVE_PATH
    ]
    unrelated_changes = [
        line
        for line in changes
        if porcelain_path(line) != SITE_X_POSTS_RELATIVE_PATH
    ]
    return {
        "changes": changes,
        "x_posts_changes": x_posts_changes,
        "unrelated_changes": unrelated_changes,
    }, None


def include_ignored_unrelated_changes(payload, worktree):
    unrelated_changes = worktree.get("unrelated_changes", []) if worktree else []
    if not unrelated_changes:
        return payload
    return {
        **payload,
        "unrelated_changes_ignored": True,
        "unrelated_changes": unrelated_changes,
    }


def publish_site_x_posts(workflow):
    publish_enabled = workflow.get("site_publish_enabled", True)
    remote = workflow.get("site_publish_remote", "origin")
    branch = workflow.get("site_publish_branch", "main")
    commit_message = workflow.get("site_publish_commit_message", "Update X posts page")
    base = {
        "enabled": publish_enabled,
        "repo": str(SITE_REPO_PATH),
        "path": str(SITE_X_POSTS_PATH),
        "published_url": SITE_PUBLISH_URL,
        "remote": remote,
        "branch": branch,
    }

    if not publish_enabled:
        return {
            **base,
            "status": "skipped_disabled",
        }

    if not (SITE_REPO_PATH / ".git").exists():
        return {
            **base,
            "status": "skipped_missing_git_repo",
        }

    current_branch = run_site_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if current_branch.returncode != 0:
        return {
            **base,
            "status": "failed_current_branch",
            **completed_process_details(current_branch),
        }

    current_branch_name = current_branch.stdout.strip()
    if current_branch_name != branch:
        return {
            **base,
            "status": "blocked_wrong_branch",
            "current_branch": current_branch_name,
        }

    worktree, status_error = inspect_site_worktree()
    if status_error:
        return {
            **base,
            **status_error,
        }
    if not worktree["x_posts_changes"]:
        return include_ignored_unrelated_changes({
            **base,
            "status": "no_changes",
        }, worktree)

    fetch = run_site_git(["fetch", remote])
    if fetch.returncode != 0:
        return {
            **base,
            "status": "failed_fetch",
            **completed_process_details(fetch),
        }

    divergence = run_site_git(["rev-list", "--left-right", "--count", f"HEAD...{remote}/{branch}"])
    if divergence.returncode != 0:
        return {
            **base,
            "status": "failed_remote_check",
            **completed_process_details(divergence),
        }

    try:
        ahead, behind = [int(value) for value in divergence.stdout.strip().split()]
    except ValueError:
        return {
            **base,
            "status": "failed_remote_check_parse",
            "raw_output": divergence.stdout.strip(),
        }

    if behind:
        return {
            **base,
            "status": "blocked_remote_changed",
            "ahead": ahead,
            "behind": behind,
        }

    add = run_site_git(["add", SITE_X_POSTS_RELATIVE_PATH])
    if add.returncode != 0:
        return {
            **base,
            "status": "failed_add",
            **completed_process_details(add),
        }

    commit = run_site_git(["commit", "-m", commit_message, "--", SITE_X_POSTS_RELATIVE_PATH])
    if commit.returncode != 0:
        return {
            **base,
            "status": "failed_commit",
            **completed_process_details(commit),
        }

    commit_hash = run_site_git(["rev-parse", "--short", "HEAD"])
    commit_id = commit_hash.stdout.strip() if commit_hash.returncode == 0 else None

    push = run_site_git(["push", remote, branch])
    if push.returncode != 0:
        return {
            **base,
            "status": "failed_push",
            "commit": commit_id,
            **completed_process_details(push),
        }

    return include_ignored_unrelated_changes({
        **base,
        "status": "pushed",
        "commit": commit_id,
        "ahead_before_commit": ahead,
    }, worktree)


def prepare_site_repo_for_publish(workflow):
    publish_enabled = workflow.get("site_publish_enabled", True)
    remote = workflow.get("site_publish_remote", "origin")
    branch = workflow.get("site_publish_branch", "main")
    base = {
        "enabled": publish_enabled,
        "repo": str(SITE_REPO_PATH),
        "remote": remote,
        "branch": branch,
    }

    if not publish_enabled:
        return {
            **base,
            "status": "skipped_disabled",
        }

    if not (SITE_REPO_PATH / ".git").exists():
        return {
            **base,
            "status": "skipped_missing_git_repo",
        }

    current_branch = run_site_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if current_branch.returncode != 0:
        return {
            **base,
            "status": "failed_current_branch",
            **completed_process_details(current_branch),
        }

    current_branch_name = current_branch.stdout.strip()
    if current_branch_name != branch:
        return {
            **base,
            "status": "blocked_wrong_branch",
            "current_branch": current_branch_name,
        }

    fetch = run_site_git(["fetch", remote])
    if fetch.returncode != 0:
        return {
            **base,
            "status": "failed_fetch",
            **completed_process_details(fetch),
        }

    divergence = run_site_git(["rev-list", "--left-right", "--count", f"HEAD...{remote}/{branch}"])
    if divergence.returncode != 0:
        return {
            **base,
            "status": "failed_remote_check",
            **completed_process_details(divergence),
        }

    try:
        ahead, behind = [int(value) for value in divergence.stdout.strip().split()]
    except ValueError:
        return {
            **base,
            "status": "failed_remote_check_parse",
            "raw_output": divergence.stdout.strip(),
        }

    if not behind:
        return {
            **base,
            "status": "up_to_date",
            "ahead": ahead,
            "behind": behind,
        }

    merge = run_site_git(["merge", "--ff-only", f"{remote}/{branch}"])
    if merge.returncode != 0:
        return {
            **base,
            "status": "failed_fast_forward",
            "ahead": ahead,
            "behind": behind,
            **completed_process_details(merge),
        }

    return {
        **base,
        "status": "fast_forwarded",
        "ahead_before": ahead,
        "behind_before": behind,
    }


def sync_preview_to_daily_curation_site(workflow):
    if not SITE_REPO_PATH.exists():
        return {
            "status": "skipped_missing_site_repo",
            "path": str(SITE_X_POSTS_PATH),
            "published_url": SITE_PUBLISH_URL,
        }

    if workflow.get("site_publish_enabled", True) and (SITE_REPO_PATH / ".git").exists():
        worktree, status_error = inspect_site_worktree()
        if status_error:
            return {
                "status": "failed_git_status",
                "path": str(SITE_X_POSTS_PATH),
                "published_url": SITE_PUBLISH_URL,
                "publish": status_error,
            }
        pre_publish = None
        if not worktree["x_posts_changes"]:
            pre_publish = prepare_site_repo_for_publish(workflow)
            if pre_publish["status"].startswith("failed_") or pre_publish["status"].startswith("blocked_"):
                return include_ignored_unrelated_changes({
                    "status": pre_publish["status"],
                    "path": str(SITE_X_POSTS_PATH),
                    "published_url": SITE_PUBLISH_URL,
                    "copied": False,
                    "pre_publish": pre_publish,
                    "publish": pre_publish,
                }, worktree)
    else:
        worktree = None
        pre_publish = None

    try:
        shutil.copyfile(PREVIEW_PATH, SITE_X_POSTS_PATH)
    except OSError as exc:
        return {
            "status": "failed_copy",
            "path": str(SITE_X_POSTS_PATH),
            "published_url": SITE_PUBLISH_URL,
            "error": str(exc),
        }

    publish_result = publish_site_x_posts(workflow)
    return include_ignored_unrelated_changes({
        "status": "synced",
        "path": str(SITE_X_POSTS_PATH),
        "published_url": SITE_PUBLISH_URL,
        "pre_publish": pre_publish,
        "publish": publish_result,
    }, worktree)


def translate_missing_archive_items(archive_path, translation_path, workflow):
    command = [
        sys.executable,
        str(TRANSLATE_SCRIPT),
        str(archive_path),
        str(translation_path),
        "--success-batch-size",
        str(workflow["translation_batch_size_success"]),
        "--failed-batch-size",
        str(workflow["translation_batch_size_failed"]),
    ]
    subprocess.run(command, check=True, env=build_translate_env())


def backfill_archive_failures(workflow):
    command = [
        sys.executable,
        str(BACKFILL_SCRIPT),
        str(ARCHIVE_PATH),
        str(DECODE_CACHE_PATH),
        "--limit",
        str(workflow["archive_backfill_retry_limit"]),
        "--min-age-minutes",
        str(workflow["archive_backfill_min_age_minutes"]),
        "--row-throttle-seconds",
        str(workflow["archive_backfill_row_throttle_seconds"]),
        "--retry-delays",
        str(workflow["archive_backfill_retry_delays"]),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    stdout = completed.stdout.strip()
    if not stdout:
        return {}
    return json.loads(stdout)


def main():
    parser = argparse.ArgumentParser(description="Run the local X watch workflow and refresh the Daily Curation preview.")
    parser.add_argument("--hours", type=int, default=None, help="Override lookback window in hours")
    parser.add_argument("--skip-rerun", action="store_true", help="Skip single-handle reruns for rate-limited accounts")
    parallel_mode = parser.add_mutually_exclusive_group()
    parallel_mode.add_argument(
        "--limited-parallel",
        dest="limited_parallel",
        action="store_true",
        default=None,
        help="Use conservative parallelism for preflight, primary low/medium handles, and reruns",
    )
    parallel_mode.add_argument(
        "--no-limited-parallel",
        dest="limited_parallel",
        action="store_false",
        help="Run the discovery stages serially even when workflow config enables limited parallelism",
    )
    parser.add_argument(
        "--preflight-concurrency",
        type=positive_int,
        default=None,
        help="Limited-parallel preflight concurrency; default 6",
    )
    parser.add_argument(
        "--primary-normal-concurrency",
        type=positive_int,
        default=None,
        help="Limited-parallel low/medium primary handle concurrency; default 3",
    )
    parser.add_argument(
        "--primary-high-concurrency",
        type=positive_int,
        default=None,
        help="Limited-parallel high-volume primary handle concurrency; default 1",
    )
    parser.add_argument(
        "--rerun-concurrency",
        type=positive_int,
        default=None,
        help="Limited-parallel rescue/rerun handle concurrency; default 2",
    )
    args = parser.parse_args()

    handles = load_json(HANDLES_CONFIG)["handles"]
    workflow = load_json(WORKFLOW_CONFIG)
    decode_cache = load_decode_cache()
    archive = load_archive()
    hours = args.hours or workflow["hours"]
    now = datetime.now().astimezone()
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir = REPORTS_DIR / f"x_watch_runs_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    limited_parallel_enabled = (
        bool(workflow.get("limited_parallel_enabled", False))
        if args.limited_parallel is None
        else args.limited_parallel
    )
    parallel_settings = {
        "enabled": limited_parallel_enabled,
        "preflight_concurrency": args.preflight_concurrency
        or workflow_positive_int(workflow, "limited_parallel_preflight_concurrency", 6),
        "primary_normal_concurrency": args.primary_normal_concurrency
        or workflow_positive_int(workflow, "limited_parallel_primary_normal_concurrency", 3),
        "primary_high_concurrency": args.primary_high_concurrency
        or workflow_positive_int(workflow, "limited_parallel_primary_high_concurrency", 1),
        "rerun_concurrency": args.rerun_concurrency
        or workflow_positive_int(workflow, "limited_parallel_rerun_concurrency", 2),
    }

    preflight_retry_delays = discover_module.parse_retry_delays(workflow["preflight_retry_delays"])
    if limited_parallel_enabled:
        preflight_infos = run_preflight_parallel(
            handles,
            hours=hours,
            now=now,
            retry_delays=preflight_retry_delays,
            concurrency=parallel_settings["preflight_concurrency"],
        )
    else:
        preflight_infos = [
            preflight_handle(handle, hours=hours, now=now, retry_delays=preflight_retry_delays)
            for handle in handles
        ]

    primary_results_by_handle = {}
    for info in preflight_infos:
        if info["handle_error"] or info["candidate_count"] == 0:
            primary_results_by_handle[info["handle"]] = synthesize_handle_result(
                info["handle"],
                hours=hours,
                summary=info["summary"],
                generated_at=now.isoformat(),
                error=info["handle_error"],
            )

    active_infos = [info for info in preflight_infos if info["candidate_count"] > 0 and not info["handle_error"]]
    active_infos.sort(
        key=lambda info: (
            info["candidate_count"],
            -(info["latest_candidate_at"].timestamp() if info["latest_candidate_at"] else 0),
            info["handle"].lower(),
        )
    )

    low_medium_infos = [
        info for info in active_infos if info["candidate_count"] <= workflow["high_candidate_threshold"]
    ]
    high_infos = [
        info for info in active_infos if info["candidate_count"] > workflow["high_candidate_threshold"]
    ]

    if limited_parallel_enabled:
        primary_results_by_handle.update(
            run_primary_parallel(
                low_medium_infos,
                hours=hours,
                workflow=workflow,
                run_dir=run_dir,
                concurrency=parallel_settings["primary_normal_concurrency"],
            )
        )
    else:
        for info in low_medium_infos:
            profile = select_primary_profile(info["candidate_count"], workflow)
            output_path = run_dir / f"primary_{info['handle']}.json"
            result = run_discover(
                [info["handle"]],
                hours=hours,
                row_throttle_seconds=profile["row_throttle_seconds"],
                retry_delays=profile["retry_delays"],
                decode_retry_cooldowns=profile["decode_retry_cooldowns"],
                output_path=output_path,
            )
            primary_results_by_handle[info["handle"]] = result
            time.sleep(profile["sleep_after_handle_seconds"])

    rescue_handles = []
    for info in low_medium_infos:
        summary = primary_results_by_handle[info["handle"]]["summary"][info["handle"]]
        if should_rescue_before_high(summary):
            rescue_handles.append(info["handle"])

    if rescue_handles:
        time.sleep(workflow["pre_high_volume_cooldown_seconds"])
        if limited_parallel_enabled:
            rescue_results = run_rerun_like_parallel(
                rescue_handles,
                hours=hours,
                workflow=workflow,
                run_dir=run_dir,
                stage="rescue",
                concurrency=parallel_settings["rerun_concurrency"],
            )
            for handle, rescue_result in rescue_results.items():
                if score_handle_result(rescue_result, handle) > score_handle_result(primary_results_by_handle[handle], handle):
                    primary_results_by_handle[handle] = rescue_result
        else:
            for handle in rescue_handles:
                output_path = run_dir / f"rescue_{handle}.json"
                rescue_result = run_discover(
                    [handle],
                    hours=hours,
                    row_throttle_seconds=workflow["rerun_row_throttle_seconds"],
                    retry_delays=workflow["rerun_retry_delays"],
                    decode_retry_cooldowns=workflow["rerun_decode_retry_cooldowns"],
                    output_path=output_path,
                )
                if score_handle_result(rescue_result, handle) > score_handle_result(primary_results_by_handle[handle], handle):
                    primary_results_by_handle[handle] = rescue_result
                time.sleep(workflow["sleep_between_handles_seconds"])

    if limited_parallel_enabled:
        primary_results_by_handle.update(
            run_primary_parallel(
                high_infos,
                hours=hours,
                workflow=workflow,
                run_dir=run_dir,
                concurrency=parallel_settings["primary_high_concurrency"],
            )
        )
    else:
        for info in high_infos:
            profile = select_primary_profile(info["candidate_count"], workflow)
            output_path = run_dir / f"primary_{info['handle']}.json"
            result = run_discover(
                [info["handle"]],
                hours=hours,
                row_throttle_seconds=profile["row_throttle_seconds"],
                retry_delays=profile["retry_delays"],
                decode_retry_cooldowns=profile["decode_retry_cooldowns"],
                output_path=output_path,
            )
            primary_results_by_handle[info["handle"]] = result
            time.sleep(profile["sleep_after_handle_seconds"])

    primary_results = [primary_results_by_handle[handle] for handle in handles]
    merged = merge_result_sets(handles, primary_results)
    apply_decode_cache(merged, decode_cache)

    if workflow["rerun_rate_limited_handles"] and not args.skip_rerun:
        rerun_handles = list_rate_limited_handles(merged)
        if limited_parallel_enabled:
            rerun_results = run_rerun_like_parallel(
                rerun_handles,
                hours=hours,
                workflow=workflow,
                run_dir=run_dir,
                stage="rerun",
                concurrency=parallel_settings["rerun_concurrency"],
            )
            for handle, rerun_result in rerun_results.items():
                apply_decode_cache(rerun_result, decode_cache)
                if score_handle_result(rerun_result, handle) > score_handle_result(merged, handle):
                    replace_handle_result(merged, rerun_result, handle)
        else:
            for handle in rerun_handles:
                output_path = run_dir / f"rerun_{handle}.json"
                rerun_result = run_discover(
                    [handle],
                    hours=hours,
                    row_throttle_seconds=workflow["rerun_row_throttle_seconds"],
                    retry_delays=workflow["rerun_retry_delays"],
                    decode_retry_cooldowns=workflow["rerun_decode_retry_cooldowns"],
                    output_path=output_path,
                )
                apply_decode_cache(rerun_result, decode_cache)
                if score_handle_result(rerun_result, handle) > score_handle_result(merged, handle):
                    replace_handle_result(merged, rerun_result, handle)
                time.sleep(workflow["sleep_between_rerun_handles_seconds"])

    merged["generated_at"] = datetime.now().astimezone().isoformat()

    latest_result_path = REPORTS_DIR / "x_watch_results_latest.json"
    timestamped_result_path = REPORTS_DIR / f"x_watch_results_{timestamp}.json"
    write_json(latest_result_path, merged)
    write_json(timestamped_result_path, merged)

    archive = update_archive(archive, merged)
    write_json(ARCHIVE_PATH, archive)

    decode_cache = update_decode_cache(decode_cache, merged)
    write_json(DECODE_CACHE_PATH, decode_cache)

    backfill_stats = {}
    if workflow.get("archive_backfill_retry_enabled", False):
        backfill_stats = backfill_archive_failures(workflow)
        archive = load_json(ARCHIVE_PATH)
        decode_cache = load_json(DECODE_CACHE_PATH)

    known_translations = load_known_translations()
    latest_translation_path = REPORTS_DIR / "x_watch_translations_latest.json"
    write_json(latest_translation_path, known_translations)

    if workflow.get("auto_translate_missing", False):
        translate_missing_archive_items(ARCHIVE_PATH, latest_translation_path, workflow)
        known_translations = load_json(latest_translation_path)

    missing_scaffold = build_missing_translation_scaffold(archive, known_translations)
    missing_translation_path = REPORTS_DIR / "x_watch_translations_missing_latest.json"
    write_json(missing_translation_path, missing_scaffold)
    write_json(REPORTS_DIR / f"x_watch_translations_missing_{timestamp}.json", missing_scaffold)
    write_json(REPORTS_DIR / f"x_watch_translations_{timestamp}.json", known_translations)

    render_preview(ARCHIVE_PATH, latest_translation_path)
    site_x_posts_sync = sync_preview_to_daily_curation_site(workflow)

    restored_from_cache_rows = sum(1 for row in merged["rows"] if row.get("restored_from_cache"))
    archive_rows_total = len(archive["rows"])

    print(json.dumps(
        {
            "handles": handles,
            "hours": hours,
            "workflow_mode": "limited_parallel" if limited_parallel_enabled else "serial",
            "parallel_settings": parallel_settings if limited_parallel_enabled else None,
            "run_dir": str(run_dir),
            "latest_result": str(latest_result_path),
            "timestamped_result": str(timestamped_result_path),
            "archive": str(ARCHIVE_PATH),
            "latest_translations": str(latest_translation_path),
            "missing_translations": str(missing_translation_path),
            "decode_cache": str(DECODE_CACHE_PATH),
            "preview": str(PREVIEW_PATH),
            "site_x_posts_sync": site_x_posts_sync,
            "restored_from_cache_rows": restored_from_cache_rows,
            "archive_rows_total": archive_rows_total,
            "new_rows_added_to_archive": archive["stats"]["new_rows_added"],
            "rows_upgraded_in_archive": archive["stats"]["rows_upgraded"],
            "archive_backfill": backfill_stats,
            "rate_limited_handles": list_rate_limited_handles(merged),
            "no_candidate_handles": list_no_candidate_handles(merged),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
