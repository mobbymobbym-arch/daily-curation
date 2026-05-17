#!/usr/bin/env python3
"""Morning gate for Daily Curation production and X Watch.

This script is intended to be called by the daily Codex automation after macOS
has been scheduled to wake. It proves that the network and local repo are ready
before starting production work, then runs the Daily Curation publish workflow
and the X Watch workflow in sequence.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
REPORTS_DIR = ROOT / "reports"
LATEST_STATUS_PATH = LOG_DIR / "morning_automation_latest.json"
NEWS_RSS_URL = (
    "https://news.google.com/rss/search"
    "?q=site%3Ax.com%2FOpenAI%20when%3A1d&hl=en-US&gl=US&ceid=US%3Aen"
)


@dataclass
class RunState:
    log_path: Path
    started_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    finished_at: str | None = None
    status: str = "running"
    preflight_attempts: list[dict[str, Any]] = field(default_factory=list)
    daily_publish: dict[str, Any] = field(default_factory=dict)
    x_watch: dict[str, Any] = field(default_factory=dict)
    git_status_after_daily: str = ""
    git_status_after_x_watch: str = ""
    failure_reason: str | None = None


def now_text() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def log(message: str, *, log_path: Path) -> None:
    line = f"[{now_text()}] {message}"
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def write_state(state: RunState) -> None:
    state.finished_at = state.finished_at or None
    payload = {
        "started_at": state.started_at,
        "finished_at": state.finished_at,
        "status": state.status,
        "failure_reason": state.failure_reason,
        "log_path": str(state.log_path),
        "preflight_attempts": state.preflight_attempts,
        "daily_publish": state.daily_publish,
        "x_watch": state.x_watch,
        "git_status_after_daily": state.git_status_after_daily,
        "git_status_after_x_watch": state.git_status_after_x_watch,
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_STATUS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def start_caffeinate(log_path: Path) -> subprocess.Popen[str] | None:
    caffeinate = shutil.which("caffeinate")
    if not caffeinate:
        log("caffeinate not found; continuing without a sleep assertion", log_path=log_path)
        return None

    try:
        process = subprocess.Popen(
            [caffeinate, "-dims", "-w", str(os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        log(f"Started caffeinate guard with pid {process.pid}", log_path=log_path)
        return process
    except OSError as exc:
        log(f"Could not start caffeinate guard: {exc}", log_path=log_path)
        return None


def stop_caffeinate(process: subprocess.Popen[str] | None, log_path: Path) -> None:
    if not process or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    log("Stopped caffeinate guard", log_path=log_path)


def check_dns(host: str, timeout_seconds: float) -> tuple[bool, str]:
    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout_seconds)
    try:
        socket.getaddrinfo(host, 443)
        return True, "ok"
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        socket.setdefaulttimeout(previous_timeout)


def check_url(url: str, timeout_seconds: float, *, method: str = "GET") -> tuple[bool, str]:
    curl = shutil.which("curl")
    if curl:
        curl_timeout = str(max(1, int(timeout_seconds)))
        if method == "HEAD":
            command = [
                curl,
                "-fsSI",
                "-L",
                "--max-time",
                curl_timeout,
                "-A",
                "DailyCurationMorningAutomation/1.0",
                url,
            ]
        else:
            command = [
                curl,
                "-fsSL",
                "--max-time",
                curl_timeout,
                "-A",
                "DailyCurationMorningAutomation/1.0",
                url,
            ]

        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                text=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds + 5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "curl timed out"
        except OSError as exc:
            return False, f"curl failed to start: {exc}"

        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            return False, f"curl exit {result.returncode}: {detail}"

        if "news.google.com/rss" in url and b"<rss" not in result.stdout and b"<feed" not in result.stdout:
            return False, "response did not look like RSS"

        return True, "curl ok"

    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": "DailyCurationMorningAutomation/1.0",
            "Accept": "application/rss+xml, text/xml, text/html;q=0.9, */*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", response.getcode())
            body = response.read(4096)
        if status >= 400:
            return False, f"http_status={status}"
        if "news.google.com/rss" in url and b"<rss" not in body and b"<feed" not in body:
            return False, "response did not look like RSS"
        return True, f"http_status={status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTPError {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return False, f"URLError: {exc.reason}"
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def check_repo_writable() -> tuple[bool, str]:
    if not ROOT.exists():
        return False, f"repo path does not exist: {ROOT}"
    if not (ROOT / "run_daily.sh").exists():
        return False, "run_daily.sh is missing"
    if not (ROOT / "scripts/run_x_watch_workflow.py").exists():
        return False, "scripts/run_x_watch_workflow.py is missing"
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        probe = LOG_DIR / ".morning_automation_write_probe"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        return False, f"log directory is not writable: {exc}"
    return True, "ok"


def run_preflight_attempt(timeout_seconds: float) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    for host in ("news.google.com", "github.com"):
        ok, detail = check_dns(host, timeout_seconds)
        checks.append({"name": f"dns:{host}", "ok": ok, "detail": detail})

    ok, detail = check_url(NEWS_RSS_URL, timeout_seconds)
    checks.append({"name": "google_news_rss", "ok": ok, "detail": detail})

    ok, detail = check_url("https://github.com/", timeout_seconds, method="HEAD")
    checks.append({"name": "github_https", "ok": ok, "detail": detail})

    ok, detail = check_repo_writable()
    checks.append({"name": "repo_writable", "ok": ok, "detail": detail})

    return {
        "checked_at": datetime.now().astimezone().isoformat(),
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }


def wait_for_readiness(
    *,
    state: RunState,
    attempts: int,
    retry_interval_seconds: int,
    timeout_seconds: float,
) -> bool:
    for attempt_number in range(1, attempts + 1):
        log(f"Preflight attempt {attempt_number}/{attempts}", log_path=state.log_path)
        attempt = run_preflight_attempt(timeout_seconds)
        attempt["attempt"] = attempt_number
        state.preflight_attempts.append(attempt)
        write_state(state)

        for check in attempt["checks"]:
            level = "OK" if check["ok"] else "FAIL"
            log(f"  {level} {check['name']}: {check['detail']}", log_path=state.log_path)

        if attempt["ok"]:
            log("Preflight passed; environment is ready", log_path=state.log_path)
            return True

        log("network not ready", log_path=state.log_path)
        if attempt_number < attempts:
            log(
                f"Waiting {retry_interval_seconds} seconds before next preflight attempt",
                log_path=state.log_path,
            )
            time.sleep(retry_interval_seconds)

    state.failure_reason = "network not ready"
    state.status = "failed_preflight"
    write_state(state)
    return False


def run_command(command: list[str], *, log_path: Path, timeout_seconds: int | None = None) -> dict[str, Any]:
    log(f"Running command: {' '.join(command)}", log_path=log_path)
    started_at = datetime.now().astimezone().isoformat()
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "DAILY_CURATION_SAFE_PUBLISH": "1",
        },
    )

    lines: list[str] = []
    timed_out = False
    deadline = time.monotonic() + timeout_seconds if timeout_seconds else None

    assert process.stdout is not None
    while True:
        line = process.stdout.readline()
        if line:
            clean_line = line.rstrip("\n")
            lines.append(clean_line)
            log(clean_line, log_path=log_path)
        if process.poll() is not None:
            remainder = process.stdout.read()
            if remainder:
                for clean_line in remainder.splitlines():
                    lines.append(clean_line)
                    log(clean_line, log_path=log_path)
            break
        if deadline and time.monotonic() > deadline:
            timed_out = True
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)
            break

    return {
        "command": command,
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(),
        "returncode": process.returncode,
        "timed_out": timed_out,
        "output": "\n".join(lines),
    }


def git_status_short() -> str:
    result = subprocess.run(
        ["git", "status", "-sb"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result.stdout.strip()


def verify_daily_publish(result: dict[str, Any]) -> tuple[bool, list[str]]:
    output = result.get("output", "")
    reasons: list[str] = []
    if result.get("returncode") != 0:
        reasons.append(f"run_daily.sh exited with {result.get('returncode')}")
    if result.get("timed_out"):
        reasons.append("run_daily.sh timed out")

    required_markers = [
        "新聞抓取完成",
        "深度分析完成",
        "翻譯完成",
        "發布完成",
        "Telegram 通知",
        "Daily Curation 全部完成",
    ]
    for marker in required_markers:
        if marker not in output:
            reasons.append(f"missing log marker: {marker}")

    status = git_status_short()
    if "ahead" in status or "behind" in status:
        reasons.append(f"git branch is not synced: {status}")

    return not reasons, reasons


def parse_last_json_object(output: str) -> dict[str, Any] | None:
    for index in [idx for idx, char in enumerate(output) if char == "{"][::-1]:
        candidate = output[index:].strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def verify_x_watch(result: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any] | None]:
    reasons: list[str] = []
    if result.get("returncode") != 0:
        reasons.append(f"run_x_watch_workflow.py exited with {result.get('returncode')}")
    if result.get("timed_out"):
        reasons.append("run_x_watch_workflow.py timed out")

    summary = parse_last_json_object(result.get("output", ""))
    if not summary:
        reasons.append("could not parse X Watch workflow summary JSON")
        return False, reasons, None

    publish_status = (
        summary.get("site_x_posts_sync", {})
        .get("publish", {})
        .get("status")
    )
    if publish_status not in {"pushed", "no_changes"}:
        reasons.append(f"unexpected X Posts publish status: {publish_status}")

    latest_result = Path(summary.get("latest_result", ""))
    latest_translations = Path(summary.get("latest_translations", ""))
    preview = Path(summary.get("preview", ""))
    for path, label in (
        (latest_result, "latest_result"),
        (latest_translations, "latest_translations"),
        (preview, "preview"),
        (ROOT / "x-posts.html", "x-posts.html"),
    ):
        if not path.exists():
            reasons.append(f"missing X Watch artifact: {label} ({path})")

    return not reasons, reasons, summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight-attempts",
        type=int,
        default=4,
        help="Number of readiness attempts. Default 4 gives 08:00, 08:05, 08:10, 08:15 when scheduled at 08:00.",
    )
    parser.add_argument(
        "--retry-interval-seconds",
        type=int,
        default=300,
        help="Delay between failed readiness attempts. Default 300 seconds.",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=20.0,
        help="Timeout for each DNS/HTTP preflight check.",
    )
    parser.add_argument(
        "--daily-timeout-seconds",
        type=int,
        default=3600,
        help="Outer timeout for run_daily.sh.",
    )
    parser.add_argument(
        "--x-watch-timeout-seconds",
        type=int,
        default=5400,
        help="Outer timeout for run_x_watch_workflow.py.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run readiness checks only; do not publish or run X Watch.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"morning_automation_{timestamp}.log"
    state = RunState(log_path=log_path)
    write_state(state)

    caffeinate_process = start_caffeinate(log_path)
    try:
        log("Morning automation started", log_path=log_path)
        log(f"Repo: {ROOT}", log_path=log_path)

        if not wait_for_readiness(
            state=state,
            attempts=args.preflight_attempts,
            retry_interval_seconds=args.retry_interval_seconds,
            timeout_seconds=args.request_timeout_seconds,
        ):
            log("Stopping before Daily Curation publish because network not ready", log_path=log_path)
            state.finished_at = datetime.now().astimezone().isoformat()
            write_state(state)
            return 20

        if args.preflight_only:
            state.status = "preflight_passed"
            state.finished_at = datetime.now().astimezone().isoformat()
            write_state(state)
            log("Preflight-only mode complete", log_path=log_path)
            return 0

        daily_result = run_command(
            ["bash", "run_daily.sh"],
            log_path=log_path,
            timeout_seconds=args.daily_timeout_seconds,
        )
        state.daily_publish = {key: value for key, value in daily_result.items() if key != "output"}
        state.git_status_after_daily = git_status_short()
        daily_ok, daily_reasons = verify_daily_publish(daily_result)
        state.daily_publish["verified"] = daily_ok
        state.daily_publish["verification_failures"] = daily_reasons
        write_state(state)

        if not daily_ok:
            state.status = "failed_daily_publish"
            state.failure_reason = "; ".join(daily_reasons)
            state.finished_at = datetime.now().astimezone().isoformat()
            write_state(state)
            log(f"Daily Curation publish verification failed: {state.failure_reason}", log_path=log_path)
            return 30

        x_watch_result = run_command(
            ["python3", "scripts/run_x_watch_workflow.py"],
            log_path=log_path,
            timeout_seconds=args.x_watch_timeout_seconds,
        )
        x_watch_ok, x_watch_reasons, x_watch_summary = verify_x_watch(x_watch_result)
        state.x_watch = {key: value for key, value in x_watch_result.items() if key != "output"}
        state.x_watch["verified"] = x_watch_ok
        state.x_watch["verification_failures"] = x_watch_reasons
        state.x_watch["summary"] = x_watch_summary
        state.git_status_after_x_watch = git_status_short()
        write_state(state)

        if not x_watch_ok:
            state.status = "failed_x_watch"
            state.failure_reason = "; ".join(x_watch_reasons)
            state.finished_at = datetime.now().astimezone().isoformat()
            write_state(state)
            log(f"X Watch verification failed: {state.failure_reason}", log_path=log_path)
            return 40

        state.status = "success"
        state.finished_at = datetime.now().astimezone().isoformat()
        write_state(state)
        log("Morning automation completed successfully", log_path=log_path)
        return 0
    finally:
        stop_caffeinate(caffeinate_process, log_path)


if __name__ == "__main__":
    sys.exit(main())
