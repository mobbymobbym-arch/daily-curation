import json
import re
import sys
from pathlib import Path


HTML_FILES = [
    Path("index.html"),
    Path("deep-analysis.html"),
    Path("podcast-highlights.html"),
    Path("x-posts.html"),
    Path("daily_curation_x_tab_preview.html"),
]

ANCHOR_RE = re.compile(r"<a\b[^>]*>", re.I)
HREF_RE = re.compile(r'\bhref=(["\'])(.*?)\1', re.I | re.S)
TARGET_RE = re.compile(r'\btarget=(["\'])_blank\1', re.I)
REL_RE = re.compile(r'\brel=(["\'])(.*?)\1', re.I | re.S)


def current_archive_file():
    data_path = Path("daily_news_temp.json")
    if not data_path.exists():
        return None
    try:
        date = json.loads(data_path.read_text(encoding="utf-8")).get("fetch_date")
    except Exception:
        return None
    if not date:
        return None
    path = Path("archives") / f"{date}.html"
    return path if path.exists() else None


def is_external_href(href):
    if href.startswith("http://") or href.startswith("https://"):
        return True
    return href.startswith("${") and re.search(r"\b(url|link|post_url|original_link)\b", href)


def rel_is_safe(anchor):
    rel_match = REL_RE.search(anchor)
    if not rel_match:
        return False
    values = set(rel_match.group(2).lower().split())
    return "noopener" in values or "noreferrer" in values


def validate_file(path):
    failures = []
    content = path.read_text(encoding="utf-8", errors="ignore")
    for line_no, line in enumerate(content.splitlines(), 1):
        for anchor in ANCHOR_RE.findall(line):
            href_match = HREF_RE.search(anchor)
            if not href_match:
                continue
            href = href_match.group(2).strip()
            if not is_external_href(href):
                continue
            if not TARGET_RE.search(anchor) or not rel_is_safe(anchor):
                failures.append(f"{path}:{line_no}: external link missing target/rel: {anchor}")
    return failures


def main():
    files = [path for path in HTML_FILES if path.exists()]
    archive = current_archive_file()
    if archive:
        files.append(archive)

    failures = []
    for path in files:
        failures.extend(validate_file(path))

    if failures:
        print("❌ External link validation failed:")
        for failure in failures:
            print(f"   {failure}")
        sys.exit(1)

    print("✅ External link validation passed.")


if __name__ == "__main__":
    main()
