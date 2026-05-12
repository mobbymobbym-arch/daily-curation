#!/usr/bin/env python3

import argparse
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path


BATCH_TIMEOUT = 180
MAX_RETRIES = 3


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def chunked(items, size):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def build_missing_requests(archive, translations):
    success_requests = []
    failed_requests = []

    success_map = translations.get("success_translations", {})
    failed_map = translations.get("failed_candidate_translations", {})

    for row in archive.get("rows", []):
        if row.get("extraction_status") == "text_extracted":
            post_url = row.get("post_url")
            if not post_url or post_url in success_map:
                continue
            success_requests.append(
                {
                    "id": post_url,
                    "handle": row.get("screen_name") or row.get("query", "").rsplit("/", 1)[-1],
                    "text": row.get("text", ""),
                    "is_truncated": bool(row.get("is_truncated")),
                }
            )
        else:
            google_news_url = row.get("google_news_url")
            if not google_news_url or google_news_url in failed_map:
                continue
            failed_requests.append(
                {
                    "id": google_news_url,
                    "handle": row.get("screen_name") or row.get("query", "").rsplit("/", 1)[-1],
                    "title": row.get("rss_title", ""),
                }
            )

    return success_requests, failed_requests


def gemini_json_request(prompt):
    proc = None
    env = os.environ.copy()
    env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"

    try:
        proc = subprocess.Popen(
            [
                "gemini",
                "-p",
                "Generate JSON only as instructed.",
                "--model",
                "gemini-3-flash-preview",
                "--output-format",
                "json",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
        stdout, stderr = proc.communicate(input=prompt, timeout=BATCH_TIMEOUT)
        if proc.returncode not in (0, None):
            raise RuntimeError(stderr.strip() or f"gemini exited with code {proc.returncode}")

        try:
            cli_response = json.loads(stdout)
            ai_output = cli_response.get("response", stdout)
        except json.JSONDecodeError:
            ai_output = stdout

        match = re.search(r"\[.*\]", ai_output, re.DOTALL)
        if not match:
            raise RuntimeError(f"could not parse JSON array from response: {ai_output[:200]}")
        return json.loads(match.group(0))
    except subprocess.TimeoutExpired as exc:
        if proc:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                proc.kill()
        raise RuntimeError("gemini translation timed out") from exc
    except Exception:
        if proc:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                proc.kill()
        raise


def normalize_batch_results(batch_items, raw_results, *, mode):
    if not isinstance(raw_results, list):
        raise RuntimeError(f"result type mismatch for {mode}: expected list, got {type(raw_results).__name__}")

    expected_ids = [item["id"] for item in batch_items]
    if len(raw_results) != len(expected_ids):
        raise RuntimeError(
            f"result count mismatch for {mode}: expected {len(expected_ids)}, got {len(raw_results)}"
        )

    normalized_by_id = {}
    for index, row in enumerate(raw_results):
        if not isinstance(row, dict):
            raise RuntimeError(
                f"result item type mismatch for {mode}: expected object at index {index}, got {type(row).__name__}"
            )

        item_id = row.get("id")
        if item_id not in expected_ids:
            raise RuntimeError(f"unexpected id for {mode}: {item_id!r}")
        if item_id in normalized_by_id:
            raise RuntimeError(f"duplicate id for {mode}: {item_id!r}")

        translation = (row.get("translation") or "").strip()
        if not translation:
            raise RuntimeError(f"empty translation for {mode}: {item_id!r}")

        normalized_by_id[item_id] = {
            "id": item_id,
            "translation": translation,
        }

    missing_ids = [item_id for item_id in expected_ids if item_id not in normalized_by_id]
    if missing_ids:
        raise RuntimeError(f"missing ids for {mode}: {missing_ids[:3]!r}")

    return [normalized_by_id[item_id] for item_id in expected_ids]


def translate_batch(batch_items, *, mode, retry_count=0):
    if not batch_items:
        return []

    if mode == "success":
        prompt = f"""
You are an expert translator for public X posts, writing fluent Taiwan Traditional Chinese (zh-TW).
Translate each post naturally and accurately.
Rules:
- Keep handles, URLs, product names, and model names in English when appropriate.
- Preserve line breaks when they help readability.
- If the source is visibly truncated, only translate the visible excerpt; do not invent missing content.
- Return exactly one output object for each input item.
- Copy each input id exactly as provided.
- Output only a valid JSON array.

INPUT ITEMS:
{json.dumps(batch_items, ensure_ascii=False, indent=2)}

OUTPUT FORMAT:
[
  {{
    "id": "original id",
    "translation": "繁體中文翻譯"
  }}
]
"""
    else:
        prompt = f"""
You are an expert translator for public X post headlines, writing fluent Taiwan Traditional Chinese (zh-TW).
Translate each visible Google News excerpt naturally.
Rules:
- Keep handles, URLs, product names, and model names in English when appropriate.
- Do not add information that is not visible in the source.
- Return exactly one output object for each input item.
- Copy each input id exactly as provided.
- Output only a valid JSON array.

INPUT ITEMS:
{json.dumps(batch_items, ensure_ascii=False, indent=2)}

OUTPUT FORMAT:
[
  {{
    "id": "original id",
    "translation": "繁體中文翻譯"
  }}
]
"""

    try:
        result = gemini_json_request(prompt)
        return normalize_batch_results(batch_items, result, mode=mode)
    except Exception:
        if retry_count < MAX_RETRIES - 1:
            time.sleep(5)
            return translate_batch(batch_items, mode=mode, retry_count=retry_count + 1)
        raise


def apply_results(translations, results, *, mode):
    target = translations["success_translations"] if mode == "success" else translations["failed_candidate_translations"]
    for row in results:
        item_id = row.get("id")
        translation = (row.get("translation") or "").strip()
        if item_id and translation:
            target[item_id] = translation


def main():
    parser = argparse.ArgumentParser(description="Translate missing X watch archive items into zh-TW.")
    parser.add_argument("archive_json")
    parser.add_argument("translations_json")
    parser.add_argument("--success-batch-size", type=int, default=30)
    parser.add_argument("--failed-batch-size", type=int, default=30)
    args = parser.parse_args()

    archive = load_json(args.archive_json)
    translations = load_json(args.translations_json)
    translations.setdefault("success_translations", {})
    translations.setdefault("failed_candidate_translations", {})

    success_requests, failed_requests = build_missing_requests(archive, translations)
    translated_success = 0
    translated_failed = 0

    for batch in chunked(success_requests, args.success_batch_size):
        results = translate_batch(batch, mode="success")
        apply_results(translations, results, mode="success")
        translated_success += len(results)

    for batch in chunked(failed_requests, args.failed_batch_size):
        results = translate_batch(batch, mode="failed")
        apply_results(translations, results, mode="failed")
        translated_failed += len(results)

    write_json(args.translations_json, translations)

    print(json.dumps(
        {
            "success_requested": len(success_requests),
            "failed_requested": len(failed_requests),
            "success_translated": translated_success,
            "failed_translated": translated_failed,
            "translations_json": args.translations_json,
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
