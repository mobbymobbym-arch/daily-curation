#!/usr/bin/env python3
"""Build the production Joyce's Daily v7 static site.

This version follows the "網頁設計優化建議" folder: green engraved masthead,
Bodoni wordmark, featured news cards, and shared chrome on section pages.
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


SITE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(os.environ.get("DAILY_CURATION_SOURCE", str(SITE_ROOT))).resolve()
OUT_DIR = Path(os.environ.get("DAILY_CURATION_OUT_DIR", str(SITE_ROOT))).resolve()
X_ARCHIVE_PATH = SOURCE_ROOT / "reports" / "x_watch_archive_latest.json"
X_TRANSLATIONS_PATH = SOURCE_ROOT / "reports" / "x_watch_translations_latest.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def strip_tags(value: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", str(value or ""), flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"#+\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def text_preview(value: str, limit: int = 300) -> str:
    text = strip_tags(value)
    return text[:limit].rstrip() + ("..." if len(text) > limit else "")


def clean_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(html.unescape(str(url)).strip())
        query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key != "access_token" and not key.startswith("utm_")
        ]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True))).rstrip("/")
    except Exception:
        return html.unescape(str(url)).strip().rstrip("/")


def normalize_date(value: str) -> str:
    match = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", str(value or ""))
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def module_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    try:
        label = path.relative_to(SITE_ROOT)
    except ValueError:
        label = path
    print(f"Wrote {label}")


def archive_rows() -> list[dict[str, str]]:
    archive_dir = SOURCE_ROOT / "archives"
    rows: list[dict[str, str]] = []
    if not archive_dir.exists():
        return rows
    for path in archive_dir.glob("*.html"):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.html", path.name):
            rows.append(
                {
                    "date": path.stem,
                    "label": path.stem,
                    "href": f"https://mobbymobbym-arch.github.io/daily-curation/archives/{path.name}",
                }
            )
    rows.sort(key=lambda item: item["date"], reverse=True)
    return rows


def load_deep_rows() -> list[dict[str, Any]]:
    rows = read_json(SOURCE_ROOT / "deep_analysis_feed.json")
    output = []
    for index, row in enumerate(rows if isinstance(rows, list) else []):
        content_html = row.get("content_html") or ""
        output.append(
            {
                "id": row.get("id") or f"analysis-{index + 1}",
                "source": row.get("source") or "Deep Analysis",
                "title": row.get("title") or "Deep Analysis",
                "url": row.get("clean_url") or clean_url(row.get("url") or ""),
                "article_date": row.get("article_date") or row.get("first_seen_date") or "",
                "first_seen_date": row.get("first_seen_date") or "",
                "latest_seen_date": row.get("latest_seen_date") or "",
                "content_html": content_html,
                "preview": row.get("preview") or text_preview(content_html),
            }
        )
    output.sort(
        key=lambda item: (
            normalize_date(item.get("article_date")),
            normalize_date(item.get("latest_seen_date")),
            normalize_date(item.get("first_seen_date")),
        ),
        reverse=True,
    )
    return output


def load_podcast_rows() -> list[dict[str, Any]]:
    rows = read_json(SOURCE_ROOT / "podcast_highlights_feed.json")
    output = []
    for index, row in enumerate(rows if isinstance(rows, list) else []):
        summary_html = row.get("summary_html") or row.get("summary") or ""
        details_html = row.get("details_html") or ""
        output.append(
            {
                "id": row.get("id") or f"podcast-{index + 1}",
                "title": row.get("title") or "Podcast Highlights",
                "show_name": row.get("show_name") or "Podcast",
                "date": row.get("generated_at") or row.get("date") or "",
                "original_link": clean_url(row.get("original_link") or row.get("url") or ""),
                "summary_html": summary_html,
                "details_html": details_html,
                "preview": row.get("preview") or text_preview(summary_html),
            }
        )
    output.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    return output


def x_handle(row: dict[str, Any]) -> str:
    if row.get("screen_name"):
        return str(row["screen_name"])
    query = str(row.get("query") or "")
    if "/" in query:
        return query.rsplit("/", 1)[-1].lstrip("@")
    return query.lstrip("@") or "x"


def parse_x_datetime(row: dict[str, Any]) -> datetime | None:
    value = str(row.get("rss_pub_date") or "")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None


def format_x_time(row: dict[str, Any]) -> str:
    parsed = parse_x_datetime(row)
    if parsed is None:
        return str(row.get("rss_pub_date") or "")
    return parsed.strftime("%Y.%m.%d %H:%M")


def x_sort_timestamp(row: dict[str, Any]) -> float:
    parsed = parse_x_datetime(row)
    return parsed.timestamp() if parsed else float("-inf")


def x_translation(row: dict[str, Any], translations: dict[str, Any]) -> str:
    success = translations.get("success_translations", {})
    failed = translations.get("failed_candidate_translations", {})
    post_url = str(row.get("post_url") or "")
    google_url = str(row.get("google_news_url") or "")
    if row.get("extraction_status") == "text_extracted" and post_url:
        return str(success.get(post_url) or "")
    return str(failed.get(google_url) or "")


def load_x_posts_from_archive() -> list[dict[str, Any]]:
    if not X_ARCHIVE_PATH.exists():
        return []
    archive = read_json(X_ARCHIVE_PATH)
    translations = read_json(X_TRANSLATIONS_PATH) if X_TRANSLATIONS_PATH.exists() else {}
    rows = archive.get("rows") if isinstance(archive, dict) else []
    if not isinstance(rows, list):
        return []

    clean_rows = []
    seen: set[str] = set()
    sorted_rows = sorted(rows, key=x_sort_timestamp, reverse=True)
    for row in sorted_rows:
        if not isinstance(row, dict):
            continue
        post_url = str(row.get("post_url") or "")
        if row.get("extraction_status") != "text_extracted" or not post_url:
            continue
        if post_url in seen:
            continue
        seen.add(post_url)
        primary_text = str(row.get("text") or row.get("rss_title") or "")
        translated = x_translation(row, translations) or primary_text
        clean_rows.append(
            {
                "id": f"x-{len(clean_rows) + 1}",
                "handle": x_handle(row),
                "display_time": format_x_time(row),
                "post_url": post_url,
                "primary_text": primary_text,
                "translation": translated,
                "show_google_news_badge": bool(row.get("is_truncated")),
            }
        )
    return clean_rows


def load_x_posts_from_legacy_html() -> list[dict[str, Any]]:
    x_html_path = SOURCE_ROOT / "x-posts.html"
    if not x_html_path.exists():
        return []
    x_html = x_html_path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(
        r'<script\s+id="x-post-rows"\s+type="application/json">([\s\S]*?)</script>',
        x_html,
    )
    if not match:
        return []
    rows = json.loads(match.group(1))
    clean_rows = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if row.get("is_failed") or not row.get("post_url"):
            continue
        key = str(row.get("post_url") or f"row-{index}")
        if key in seen:
            continue
        seen.add(key)
        clean_rows.append(
            {
                "id": f"x-{len(clean_rows) + 1}",
                "handle": row.get("handle") or "x",
                "display_time": row.get("display_time") or "",
                "post_url": row.get("post_url") or "",
                "primary_text": row.get("primary_text") or "",
                "translation": row.get("translation") or row.get("primary_text") or "",
                "show_google_news_badge": bool(row.get("show_google_news_badge")),
            }
        )
    return clean_rows


def load_x_posts() -> list[dict[str, Any]]:
    return load_x_posts_from_archive() or load_x_posts_from_legacy_html()


def load_news_data(deep_rows: list[dict[str, Any]], podcast_rows: list[dict[str, Any]]) -> dict[str, Any]:
    data = read_json(SOURCE_ROOT / "daily_news_temp.json")
    return {
        "date": data.get("fetch_date") or "",
        "techmeme": data.get("techmeme") or [],
        "wsj": data.get("wsj") or [],
        "analysis": deep_rows[:3],
        "podcast": podcast_rows[:2],
        "archives": archive_rows(),
    }


STYLE_CSS = r"""
:root {
  --bg: #f5f2e8;
  --panel: #e7eede;
  --ink: #16201a;
  --muted: #687069;
  --card: #fffef8;
  --line: #e3ddc9;
  --news: #155e48;
  --edit: #2f7d5b;
  --gold: #9c7b2e;
  --green-soft: #d8e5d6;
  --chip: #e9ead3;
  --shadow-card: 0 10px 24px rgba(0, 0, 0, .07);
  --shadow-button: 0 10px 22px rgba(0, 0, 0, .10);
  color-scheme: light;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1411;
    --panel: #15201a;
    --ink: #eef2ea;
    --muted: #969e95;
    --card: #161f19;
    --line: #29322b;
    --news: #62c39a;
    --edit: #79c79e;
    --gold: #cdab5e;
    --green-soft: #20302a;
    --chip: #1f281f;
    --shadow-card: 0 12px 28px rgba(0, 0, 0, .32);
    --shadow-button: 0 10px 22px rgba(0, 0, 0, .28);
    color-scheme: dark;
  }
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: "Schibsted Grotesk", "Noto Sans TC", system-ui, -apple-system, sans-serif;
  line-height: 1.6;
  letter-spacing: 0;
  -webkit-font-smoothing: antialiased;
}
a { color: inherit; }
button { font: inherit; }
.skip-link {
  position: absolute;
  left: 16px;
  top: 10px;
  z-index: 1000;
  transform: translateY(-150%);
  background: var(--news);
  color: #fff;
  border-radius: 999px;
  padding: 8px 14px;
  text-decoration: none;
}
.skip-link:focus { transform: translateY(0); }
.site-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  padding: 9px 0;
  border-bottom: 1px solid var(--line);
  background: color-mix(in srgb, var(--bg) 80%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.nav-inner {
  max-width: 1320px;
  margin: 0 auto;
  position: relative;
  padding: 0 56px 0 16px;
}
.nav-links {
  display: flex;
  gap: 7px;
  row-gap: 7px;
  justify-content: center;
  flex-wrap: wrap;
}
.nav-pill {
  text-decoration: none;
  font-weight: 700;
  font-size: .7rem;
  text-transform: uppercase;
  letter-spacing: .4px;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 6px 13px;
  border-radius: 999px;
  border: 1px solid transparent;
  background: var(--chip);
  color: var(--ink);
  transition: background .2s ease, color .2s ease, transform .2s ease, box-shadow .2s ease;
}
.nav-pill:hover { transform: translateY(-1px); }
.nav-pill.is-active {
  background: var(--news);
  color: #fff;
  box-shadow: var(--shadow-button);
}
.home-orb {
  position: absolute;
  top: 50%;
  right: 16px;
  transform: translateY(-50%);
  width: 32px;
  height: 32px;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  color: var(--news);
  background: var(--card);
  border: 1px solid var(--line);
  font-size: .9rem;
}
.masthead {
  position: relative;
  overflow: hidden;
  text-align: center;
  padding: 48px 32px 42px;
  background: radial-gradient(125% 95% at 50% 0%, #1b5e46 0%, #0c3527 72%);
}
.masthead::before {
  content: "";
  position: absolute;
  inset: 0;
  opacity: .55;
  pointer-events: none;
  background-image:
    repeating-radial-gradient(circle at 50% 20%, transparent 0 7px, rgba(206, 170, 92, .10) 7px 8px),
    repeating-linear-gradient(48deg, rgba(255, 255, 255, .035) 0 1px, transparent 1px 12px),
    repeating-linear-gradient(-48deg, rgba(255, 255, 255, .025) 0 1px, transparent 1px 12px);
}
.masthead::after {
  content: "";
  position: absolute;
  inset: 14px;
  border: 1px solid rgba(206, 170, 92, .5);
  pointer-events: none;
  box-shadow: inset 0 0 0 5px rgba(206, 170, 92, .04);
}
.masthead-inner {
  position: relative;
  color: #f1ecdd;
}
.masthead-badge {
  width: 62px;
  height: 62px;
  margin: 0 auto 16px;
  border-radius: 50%;
  border: 1.5px solid #cdaa5c;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  box-shadow: 0 0 0 5px rgba(206, 170, 92, .12);
}
.masthead-badge::before {
  content: "";
  position: absolute;
  inset: 5px;
  border-radius: 50%;
  border: 1px solid rgba(206, 170, 92, .55);
}
.masthead-badge span {
  font-family: "Bodoni Moda", Didot, serif;
  font-weight: 600;
  font-size: 1.32rem;
  color: #e6c87e;
  letter-spacing: .5px;
}
.masthead-kicker {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 13px;
  margin-bottom: 8px;
}
.masthead-kicker span.line {
  height: 1px;
  width: 60px;
  background: linear-gradient(to right, transparent, #cdaa5c);
}
.masthead-kicker span.line:last-child {
  background: linear-gradient(to left, transparent, #cdaa5c);
}
.masthead-kicker strong {
  font-size: .64rem;
  font-weight: 700;
  letter-spacing: 4px;
  text-transform: uppercase;
  white-space: nowrap;
  color: #cdaa5c;
}
.diamond { color: #cdaa5c; font-size: .6rem; }
.wordmark {
  font-family: "Bodoni Moda", Didot, serif;
  font-style: italic;
  font-weight: 500;
  font-size: clamp(2.8rem, 6vw, 4.2rem);
  line-height: 1.04;
  letter-spacing: .5px;
  margin: 0;
  color: #f4efe1;
}
.wordmark span { color: #e6c87e; }
.fleuron {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
}
.fleuron span {
  height: 1px;
  width: 30px;
  background: rgba(241, 236, 221, .4);
}
.fleuron b {
  color: #cdaa5c;
  font-size: .95rem;
  line-height: 1;
}
.masthead-meta {
  margin-top: 14px;
  font-size: .8rem;
  font-weight: 600;
  letter-spacing: 2px;
  color: rgba(241, 236, 221, .74);
}
.home-shell {
  max-width: 1320px;
  margin: 0 auto;
  padding: 8px 24px 96px;
}
.reading-shell {
  max-width: 780px;
  margin: 0 auto;
  padding: 36px 22px 110px;
}
.section-heading {
  display: flex;
  align-items: baseline;
  gap: 16px;
  flex-wrap: wrap;
  margin: 58px 0 22px;
  color: var(--news);
}
.section-heading.is-edit { color: var(--edit); }
.section-heading h2 {
  font-family: "Newsreader", Georgia, serif;
  font-weight: 600;
  font-size: 1.85rem;
  margin: 0;
  color: var(--ink);
}
.section-date,
.feed-count {
  margin-left: auto;
  font-size: .82rem;
  font-weight: 600;
  color: var(--muted);
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.featured-card {
  background: linear-gradient(135deg, var(--card), color-mix(in srgb, var(--green-soft) 55%, var(--card)));
  border: 1px solid var(--line);
  border-radius: 16px;
  overflow: hidden;
  margin-bottom: 13px;
  box-shadow: 0 8px 24px rgba(21, 94, 72, .08);
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr));
  transition: box-shadow .2s ease, border-color .2s ease;
}
.featured-card:hover {
  border-color: var(--news);
  box-shadow: 0 16px 38px rgba(21, 94, 72, .14);
}
.featured-media {
  position: relative;
  min-height: 260px;
  background: var(--chip);
  border-right: 1px dashed rgba(22, 32, 26, .18);
  overflow: hidden;
}
.featured-media.has-image {
  background: #12231b;
  border-right: 0;
}
.featured-media.has-image::after {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background: linear-gradient(180deg, rgba(0,0,0,.24), rgba(0,0,0,.08) 46%, rgba(0,0,0,.44));
}
.featured-media.has-image.image-failed {
  background: var(--chip);
  border-right: 1px dashed rgba(22, 32, 26, .18);
}
.featured-media.has-image.image-failed::after,
.featured-media.has-image.image-contain::after,
.featured-media.has-image.image-too-small::after {
  display: none;
}
.featured-media.has-image.image-too-small {
  background: var(--chip);
  border-right: 1px dashed rgba(22, 32, 26, .18);
}
.featured-image {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center center;
  display: block;
}
.featured-media.image-contain .featured-image {
  object-fit: contain;
}
.featured-media.image-cover .featured-image {
  object-fit: cover;
  object-position: center top;
}
.featured-media.image-too-small .featured-image,
.featured-media.image-too-small .image-credit {
  display: none;
}
.feature-badge {
  position: absolute;
  top: 16px;
  left: 16px;
  z-index: 2;
  background: var(--news);
  color: #fff;
  border-radius: 999px;
  padding: 5px 13px;
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .6px;
}
.image-credit {
  position: absolute;
  right: 12px;
  bottom: 10px;
  z-index: 2;
  max-width: calc(100% - 24px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border-radius: 999px;
  padding: 5px 10px;
  background: rgba(14, 20, 16, .68);
  color: rgba(255,255,255,.84);
  font-size: .68rem;
  font-weight: 600;
}
.placeholder-mark {
  min-height: 260px;
  height: 100%;
  display: grid;
  place-items: center;
  text-align: center;
  color: var(--muted);
  font-size: .84rem;
}
.featured-media.has-image .placeholder-mark {
  display: none;
}
.featured-media.has-image.image-failed .placeholder-mark {
  display: grid;
}
.featured-media.has-image.image-too-small .placeholder-mark {
  display: grid;
}
.placeholder-mark i {
  display: block;
  margin-bottom: 8px;
  font-size: 1.35rem;
  opacity: .55;
}
.featured-copy {
  padding: 30px 32px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 12px;
}
.source-label {
  font-size: .74rem;
  font-weight: 700;
  letter-spacing: .5px;
  text-transform: uppercase;
  color: var(--news);
}
.featured-title {
  font-family: "Newsreader", Georgia, serif;
  font-weight: 600;
  font-size: clamp(1.35rem, 2.4vw, 1.8rem);
  line-height: 1.32;
  margin: 0;
  color: var(--ink);
  overflow-wrap: anywhere;
  word-break: break-word;
}
.featured-subtitle,
.news-subtitle {
  font-size: .92rem;
  line-height: 1.6;
  color: var(--muted);
  overflow-wrap: anywhere;
  word-break: break-word;
}
.news-grid,
.teaser-grid {
  display: grid;
  gap: 13px;
}
.news-grid {
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 390px), 1fr));
}
.teaser-grid {
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
}
.news-row {
  display: flex;
  flex-direction: column;
  gap: 7px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 17px 19px;
  text-decoration: none;
  transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
  min-width: 0;
}
.news-row:hover,
.feed-card:hover,
.x-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-card);
  border-color: var(--news);
}
.news-title {
  font-size: 1.04rem;
  font-weight: 600;
  line-height: 1.45;
  color: var(--ink);
  overflow-wrap: anywhere;
  word-break: break-word;
}
.news-source {
  margin-top: 3px;
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .5px;
  text-transform: uppercase;
  color: var(--news);
}
.feed-card,
.x-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 26px;
  min-width: 0;
  transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
}
.home-teaser {
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  padding: 24px;
}
.home-teaser > .chip {
  align-self: flex-start;
  margin-bottom: 18px;
}
.chip {
  display: inline-flex;
  align-items: center;
  background: var(--edit);
  color: #fff;
  border-radius: 999px;
  padding: 5px 12px;
  font-size: .74rem;
  font-weight: 700;
  line-height: 1.2;
  max-width: 100%;
}
.chip-neutral {
  background: var(--chip);
  color: var(--ink);
}
.card-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}
.card-date {
  color: var(--muted);
  font-size: .82rem;
  font-weight: 600;
}
.feed-card h3 {
  font-family: "Newsreader", Georgia, serif;
  font-weight: 600;
  font-size: 1.32rem;
  line-height: 1.42;
  margin: 0 0 14px;
  color: var(--ink);
  overflow-wrap: anywhere;
}
.card-summary {
  color: var(--ink);
  opacity: .78;
  font-size: .96rem;
  line-height: 1.82;
  margin: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.home-teaser .card-summary {
  flex: 1;
  margin-bottom: 18px;
}
.card-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}
.pill {
  border: 1px solid var(--edit);
  cursor: pointer;
  font-family: inherit;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border-radius: 999px;
  min-height: 40px;
  padding: 9px 18px;
  font-size: .82rem;
  font-weight: 700;
  color: var(--edit);
  background: transparent;
  transition: background .2s ease, color .2s ease, border-color .2s ease, box-shadow .2s ease, transform .2s ease;
}
.pill:hover {
  background: var(--edit);
  color: var(--bg);
  box-shadow: var(--shadow-button);
  transform: translateY(-1px);
}
.pill-news {
  color: var(--news);
  border-color: var(--news);
}
.pill-news:hover {
  background: var(--news);
  color: #fff;
}
.pill-soft {
  border: none;
  background: var(--chip);
  color: var(--edit);
}
.pill-filled {
  border: none;
  color: #fff;
  background: var(--edit);
  padding: 14px 30px;
  font-size: .92rem;
}
.pill-ink {
  border: none;
  color: var(--bg);
  background: var(--ink);
  padding: 14px 30px;
  font-size: .92rem;
}
.article-body {
  overflow-wrap: anywhere;
  word-break: break-word;
}
.article-body p {
  margin: 0 0 1.05rem;
  color: var(--ink);
  opacity: .86;
  font-size: .96rem;
  line-height: 1.85;
}
.article-body p:last-child { margin-bottom: 0; }
.article-body h3,
.article-body h4,
.article-body .analysis-subheading {
  margin: 1.5rem 0 .6rem;
  font-weight: 700;
  font-size: 1.05rem;
  line-height: 1.5;
  color: var(--ink);
}
.article-body h3:first-child,
.article-body h4:first-child,
.article-body .analysis-subheading:first-child { margin-top: 0; }
.article-body h3 span {
  background: var(--chip);
  color: var(--edit);
  padding: 2px 8px;
  border-radius: 8px;
  margin-right: 8px;
  font-size: .92rem;
}
.article-body a {
  color: var(--edit);
  text-decoration: none;
  font-weight: 600;
}
.article-body a:hover { text-decoration: underline; }
.article-body blockquote {
  margin: 14px 0;
  padding: 12px 16px;
  border-left: 3px solid var(--edit);
  background: var(--chip);
  border-radius: 0 8px 8px 0;
  font-style: italic;
  color: var(--muted);
}
.article-body strong { color: var(--ink); }
.feed-stack {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 18px;
}
.load-row {
  display: flex;
  justify-content: center;
  margin-top: 30px;
}
.x-top {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.x-time {
  margin-left: auto;
  color: var(--muted);
  font-size: .84rem;
  font-weight: 600;
}
.x-copy {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.x-translation {
  font-size: 1.04rem;
  line-height: 1.8;
  color: var(--ink);
}
.x-original {
  font-size: .86rem;
  line-height: 1.7;
  color: var(--muted);
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}
.x-link-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.x-link {
  color: var(--ink);
  border-color: var(--line);
  min-height: 32px;
  padding: 7px 15px;
  font-size: .78rem;
}
.x-link:hover {
  background: var(--ink);
  color: var(--bg);
  border-color: var(--ink);
}
.open-icon { transform: rotate(45deg); font-size: .7rem; }
.archive-section {
  max-width: 1320px;
  margin: 40px auto 0;
  padding: 48px 24px 0;
  border-top: 1px solid var(--line);
}
.archive-box {
  max-width: 560px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 30px 32px;
}
.archive-box h3 {
  font-family: "Newsreader", Georgia, serif;
  font-weight: 600;
  font-size: 1.35rem;
  margin: 0 0 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--ink);
}
.archive-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.archive-list.is-collapsed li:nth-child(n + 8) { display: none; }
.archive-list li { border-bottom: 1px solid var(--line); }
.archive-list a {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: var(--ink);
  padding: 11px 2px;
  font-weight: 500;
}
.archive-list a:hover { color: var(--news); }
.archive-toggle {
  width: 100%;
  margin-top: 16px;
  min-height: 44px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--chip);
  color: var(--news);
  font-weight: 700;
  font-size: .85rem;
  cursor: pointer;
  font-family: inherit;
}
.site-footer {
  text-align: center;
  padding: 48px 24px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: .9rem;
}
.site-footer p { margin: 0; }
@media (max-width: 768px) {
  .nav-inner { padding: 0 14px; }
  .home-orb { display: none; }
  .nav-links { justify-content: flex-start; }
  .masthead {
    padding: 42px 18px 38px;
  }
  .masthead-kicker span.line {
    width: 38px;
  }
  .masthead-meta {
    font-size: .72rem;
    letter-spacing: 1.2px;
  }
  .home-shell {
    padding: 6px 14px 78px;
  }
  .reading-shell {
    padding: 32px 14px 86px;
  }
  .section-heading {
    align-items: flex-start;
    margin-top: 48px;
  }
  .section-date,
  .feed-count {
    margin-left: 0;
  }
  .featured-copy {
    padding: 26px 22px;
  }
  .featured-media {
    border-right: 0;
    border-bottom: 1px dashed rgba(22, 32, 26, .18);
  }
  .feed-card,
  .x-card {
    padding: 22px;
  }
  .x-time {
    margin-left: 0;
  }
}
"""


APP_JS = r"""
import { newsData } from "../data/news.js";
import { deepRows } from "../data/deep-analysis.js";
import { podcastRows } from "../data/podcast-highlights.js";
import { xRows } from "../data/x-posts.js";

const page = document.body.dataset.page || "home";
const app = document.getElementById("app");
const pageState = { visible: 12, xVisible: 40, expanded: {}, archiveOpen: false };

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function externalAttrs(url) {
  return /^https?:\/\//i.test(String(url || "")) ? ' target="_blank" rel="noopener noreferrer"' : "";
}

function openIcon() {
  return '<i class="fas fa-arrow-up open-icon" aria-hidden="true"></i>';
}

// Future headline-image pipeline hooks. Keep these slot ids stable:
// - homepage-featured-techmeme: homepage Techmeme lead story image
// - homepage-featured-wsj: homepage WSJ lead story image
const HEADLINE_IMAGE_SLOTS = {
  "feat-techmeme": "homepage-featured-techmeme",
  "feat-wsj": "homepage-featured-wsj",
};

const HEADLINE_FALLBACK_IMAGES = {
  "feat-techmeme": {
    url: "assets/images/fallback-techmeme-headline.png",
    alt: "Techmeme live technology news fallback graphic",
  },
};

function titleText(item) {
  return item.title_zh || item.title_en || item.cn || "Untitled";
}

function subtitleText(item) {
  if (item.title_zh && item.title_en && item.title_zh !== item.title_en) return item.title_en;
  return item.summary_zh || item.summary_en || item.en || "";
}

function imageText(item) {
  return imageInfo(item).url;
}

function imageCreditText(item) {
  return imageInfo(item).credit;
}

function imageInfo(item, slotId = "") {
  const heroImage = item.image_url || item.hero_image_url || item.image || "";
  if (heroImage) {
    return {
      url: heroImage,
      kind: "hero",
      alt: item.image_alt || "",
      credit: item.image_credit || "",
    };
  }

  const fallback = HEADLINE_FALLBACK_IMAGES[slotId];
  return {
    url: fallback?.url || "",
    kind: fallback ? "fallback" : "",
    alt: fallback?.alt || "",
    credit: "",
  };
}

const HERO_MIN_IMAGE_WIDTH = 420;
const HERO_MIN_IMAGE_HEIGHT = 180;

function hideFeaturedImage(image, className) {
  const media = image.closest(".featured-media");
  if (!media) return;
  media.classList.add(className);
  image.remove();
}

function evaluateFeaturedImage(image) {
  const media = image.closest(".featured-media");
  if (!media) return;

  const width = image.naturalWidth || 0;
  const height = image.naturalHeight || 0;
  if (!width || !height) {
    hideFeaturedImage(image, "image-failed");
    return;
  }

  if (width < HERO_MIN_IMAGE_WIDTH || height < HERO_MIN_IMAGE_HEIGHT) {
    hideFeaturedImage(image, "image-too-small");
    return;
  }

  const mediaRatio = media.clientWidth && media.clientHeight ? media.clientWidth / media.clientHeight : 0;
  const imageRatio = width / height;
  media.classList.add(mediaRatio && imageRatio < mediaRatio * 0.86 ? "image-contain" : "image-cover");
}

function setupFeaturedImages(root = document) {
  root.querySelectorAll(".featured-image").forEach((image) => {
    image.addEventListener("load", () => evaluateFeaturedImage(image), { once: true });
    image.addEventListener("error", () => hideFeaturedImage(image, "image-failed"), { once: true });
    if (image.complete) {
      if (image.naturalWidth) evaluateFeaturedImage(image);
      else hideFeaturedImage(image, "image-failed");
    }
  });
}

function dateText(value) {
  return escapeHtml(String(value || "").replace("T", " ").trim());
}

function renderNav(active) {
  const items = [
    { key: "techmeme", label: "Techmeme", href: page === "home" ? "#techmeme-section" : "index.html#techmeme-section" },
    { key: "wsj", label: "WSJ Tech", href: page === "home" ? "#wsj-section" : "index.html#wsj-section" },
    { key: "analysis", label: "Deep Analysis", href: "deep-analysis.html" },
    { key: "podcast", label: "Podcast", href: "podcast-highlights.html" },
    { key: "x", label: "X Posts", href: "x-posts.html" },
  ];
  return `
    <a class="skip-link" href="#app">Skip to content</a>
    <nav class="site-nav" aria-label="Primary navigation">
      <div class="nav-inner">
        <div class="nav-links">
          ${items.map((item) => {
            const on = item.key === active;
            return `<a class="nav-pill${on ? " is-active" : ""}" href="${item.href}"${on ? ' aria-current="page"' : ""}>${item.label}</a>`;
          }).join("")}
        </div>
        <a class="home-orb" href="index.html" aria-label="回到策展首頁" title="首頁"><i class="fas fa-home" aria-hidden="true"></i></a>
      </div>
    </nav>
  `;
}

function renderMasthead({ active = "techmeme", storyCount = null } = {}) {
  const meta = storyCount ? `${escapeHtml(newsData.date)} | 共 ${storyCount} 則精選` : escapeHtml(newsData.date);
  return `
    ${renderNav(active)}
    <header class="masthead">
      <div aria-hidden="true" style="position:absolute; inset:19px; border:1px solid rgba(206,170,92,.22); pointer-events:none;"></div>
      <div class="masthead-inner">
        <div class="masthead-badge"><span>JD</span></div>
        <div class="masthead-kicker">
          <span class="line"></span><span class="diamond">&#9670;</span><strong>每日科技精選</strong><span class="diamond">&#9670;</span><span class="line"></span>
        </div>
        <h1 class="wordmark">Joyce&rsquo;s <span>Daily</span></h1>
        <div class="fleuron"><span></span><b>&#10086;</b><span></span></div>
        <div class="masthead-meta">${meta}</div>
      </div>
    </header>
  `;
}

function mountMasthead(options) {
  if (document.querySelector(".masthead")) return;
  document.body.insertAdjacentHTML("afterbegin", renderMasthead(options));
}

function sectionHeading({ id, icon, title, date, edit = false, count = "" }) {
  return `
    <div id="${id}" class="section-heading${edit ? " is-edit" : ""}">
      ${icon ? `<i class="fas ${icon}" aria-hidden="true"></i>` : ""}
      <h2>${escapeHtml(title)}</h2>
      ${date ? `<span class="section-date"><i class="far fa-calendar-alt" aria-hidden="true"></i>${escapeHtml(date)}</span>` : ""}
      ${count ? `<span class="feed-count">${escapeHtml(count)}</span>` : ""}
    </div>
  `;
}

function featuredCard(item, slotId) {
  const url = item.url || "#";
  const source = item.source || item.media_source || (slotId === "feat-wsj" ? "Wall Street Journal" : "Source");
  const title = titleText(item);
  const subtitle = subtitleText(item);
  const image = imageInfo(item, slotId);
  const imageSlot = HEADLINE_IMAGE_SLOTS[slotId] || slotId;
  return `
    <article class="featured-card">
      <div class="featured-media${image.url ? " has-image" : ""}">
        <span class="feature-badge">頭條</span>
        <!-- HEADLINE_IMAGE_SLOT ${imageSlot}: populated from item.image_url when available. -->
        ${image.url ? `<img class="featured-image" src="${escapeHtml(image.url)}" alt="${escapeHtml(image.alt || title)}" loading="lazy" referrerpolicy="no-referrer">` : ""}
        ${image.credit ? `<div class="image-credit">${escapeHtml(image.credit)}</div>` : ""}
        <div class="placeholder-mark" data-slot="${slotId}" data-image-slot="${imageSlot}" data-image-role="homepage-lead-image">
          <div><i class="far fa-image" aria-hidden="true"></i><span>拖入頭條配圖</span><br><small>or browse files</small></div>
        </div>
      </div>
      <div class="featured-copy">
        <div class="source-label">${escapeHtml(source)}</div>
        <a href="${escapeHtml(url)}"${externalAttrs(url)} style="text-decoration:none;">
          <h3 class="featured-title">${escapeHtml(title)}</h3>
        </a>
        ${subtitle ? `<div class="featured-subtitle">${escapeHtml(subtitle)}</div>` : ""}
        <a class="pill pill-news" href="${escapeHtml(url)}"${externalAttrs(url)}>閱讀全文 &rarr;</a>
      </div>
    </article>
  `;
}

function newsRow(item, fallbackSource) {
  const url = item.url || "#";
  const source = item.source || item.media_source || fallbackSource;
  const subtitle = subtitleText(item);
  return `
    <a class="news-row" href="${escapeHtml(url)}"${externalAttrs(url)}>
      <div class="news-title">${escapeHtml(titleText(item))}</div>
      ${subtitle ? `<div class="news-subtitle">${escapeHtml(subtitle)}</div>` : ""}
      <div class="news-source">${escapeHtml(source)} &rarr;</div>
    </a>
  `;
}

function homeTeaser(row, kind) {
  const isPodcast = kind === "podcast";
  const chip = isPodcast ? row.show_name || "Podcast" : row.source || "Deep Analysis";
  const date = isPodcast ? row.date : row.article_date || row.first_seen_date || row.latest_seen_date || "";
  const href = isPodcast ? row.original_link : row.url;
  const hrefLabel = isPodcast ? "Listen" : chip;
  const historyHref = isPodcast ? "podcast-highlights.html" : "deep-analysis.html";
  return `
    <article class="feed-card home-teaser">
      <span class="chip">${escapeHtml(chip)}</span>
      <h3>${escapeHtml(row.title)}</h3>
      <div class="card-date" style="margin-bottom:14px;">${dateText(date)}</div>
      <p class="card-summary">${escapeHtml(row.preview || "")}</p>
      <div style="display:flex; gap:18px; flex-wrap:wrap; align-items:center; margin-top:auto;">
        ${href ? `<a href="${escapeHtml(href)}"${externalAttrs(href)} style="text-decoration:none; font-size:.78rem; font-weight:700; letter-spacing:.4px; text-transform:uppercase; color:var(--edit);">${escapeHtml(hrefLabel)} &rarr;</a>` : ""}
        <a href="${historyHref}" style="text-decoration:none; font-size:.78rem; font-weight:700; letter-spacing:.4px; text-transform:uppercase; color:var(--muted);">Read history &rarr;</a>
      </div>
    </article>
  `;
}

function renderArchives() {
  const rows = newsData.archives || [];
  const visible = pageState.archiveOpen ? rows : rows.slice(0, 7);
  return `
    <section class="archive-section">
      <div class="archive-box">
        <h3><i class="fas fa-folder-open" aria-hidden="true" style="color:var(--news); font-size:1.05rem;"></i>日報存檔</h3>
        <ul class="archive-list${pageState.archiveOpen ? "" : " is-collapsed"}">
          ${visible.map((row) => `
            <li><a href="${escapeHtml(row.href)}"${externalAttrs(row.href)}><i class="far fa-file-lines" aria-hidden="true" style="color:var(--muted); font-size:.85rem;"></i>${escapeHtml(row.label)}</a></li>
          `).join("")}
        </ul>
        ${rows.length > 7 ? `<button class="archive-toggle" type="button" data-archive-toggle>${pageState.archiveOpen ? "收合存檔" : "顯示更多存檔"}</button>` : ""}
      </div>
    </section>
  `;
}

function renderHome() {
  const techmeme = newsData.techmeme || [];
  const wsj = newsData.wsj || [];
  mountMasthead({ active: "techmeme", storyCount: techmeme.length + wsj.length });
  app.className = "home-shell";
  app.innerHTML = `
    ${sectionHeading({ id: "techmeme-section", icon: "fa-bolt", title: "Techmeme Main Feed", date: newsData.date })}
    ${techmeme.length ? featuredCard(techmeme[0], "feat-techmeme") : ""}
    <div class="news-grid">${techmeme.slice(1).map((item) => newsRow(item, "Techmeme")).join("")}</div>
    ${sectionHeading({ id: "wsj-section", icon: "fa-newspaper", title: "WSJ Technology Top 10", date: newsData.date })}
    ${wsj.length ? featuredCard(wsj[0], "feat-wsj") : ""}
    <div class="news-grid">${wsj.slice(1).map((item) => newsRow(item, "WSJ")).join("")}</div>
    ${sectionHeading({ id: "analysis-section", icon: "fa-feather-alt", title: "Deep Analysis", edit: true })}
    <div class="teaser-grid">${(newsData.analysis || []).map((row) => homeTeaser(row, "analysis")).join("")}</div>
    ${sectionHeading({ id: "podcast-section", icon: "fa-microphone-alt", title: "Podcast Highlights", edit: true, count: (newsData.podcast?.[0]?.date || "").slice(0, 10) })}
    <div class="teaser-grid">${(newsData.podcast || []).map((row) => homeTeaser(row, "podcast")).join("")}</div>
  `;
  setupFeaturedImages(app);
  document.body.insertAdjacentHTML("beforeend", renderArchives() + '<footer class="site-footer"><p>由 Doraemon-Mobby 為 Joyce 精心策展</p></footer>');
  setupHomeSpy();
}

function renderArticleCard(row, kind) {
  const isPodcast = kind === "podcast";
  const expanded = !!pageState.expanded[row.id];
  const hasDetails = isPodcast ? Boolean(row.details_html && row.details_html.trim()) : Boolean(row.content_html);
  const chip = isPodcast ? row.show_name || "Podcast" : row.source || "Deep Analysis";
  const date = isPodcast ? row.date : row.article_date || row.first_seen_date || row.latest_seen_date || "";
  const url = isPodcast ? row.original_link : row.url;
  const label = isPodcast ? "Listen" : "Original";
  const summary = isPodcast
    ? `<div class="article-body">${row.summary_html || escapeHtml(row.preview || "")}</div>`
    : `<p class="card-summary">${escapeHtml(row.preview || "")}</p>`;
  const body = isPodcast ? row.details_html : row.content_html;
  return `
    <article class="feed-card">
      <div class="card-meta"><span class="chip">${escapeHtml(chip)}</span><span class="card-date">${dateText(date)}</span></div>
      <h3>${escapeHtml(row.title)}</h3>
      ${summary}
      ${expanded && hasDetails ? `<div class="article-body" style="margin-top:14px; padding-top:14px; border-top:1px dashed var(--line);">${body || ""}</div>` : ""}
      <div class="card-actions">
        ${hasDetails ? `<button class="pill pill-soft" type="button" data-toggle="${escapeHtml(row.id)}">${expanded ? (isPodcast ? "收合內容" : "收合全文") : "展開全文"}</button>` : "<span></span>"}
        ${url ? `<a class="pill" href="${escapeHtml(url)}"${externalAttrs(url)}>${label} &rarr;</a>` : ""}
      </div>
    </article>
  `;
}

function renderFeedPage({ rows, active, title, icon, kind }) {
  mountMasthead({ active });
  app.className = "reading-shell";
  const shown = rows.slice(0, pageState.visible);
  app.innerHTML = `
    ${sectionHeading({ id: "feed-title", icon, title, edit: active !== "x", count: `目前顯示 ${shown.length} / ${rows.length}` })}
    <div class="feed-stack">${shown.map((row) => renderArticleCard(row, kind)).join("")}</div>
    ${pageState.visible < rows.length ? `<div class="load-row"><button class="pill pill-filled" type="button" data-load-more>載入更多</button></div>` : ""}
  `;
}

function xCard(row) {
  return `
    <article class="x-card">
      <div class="x-top">
        <span class="chip chip-neutral">@${escapeHtml(row.handle)}</span>
        ${row.show_google_news_badge ? '<span class="chip chip-neutral" style="color:var(--muted); font-size:.72rem;">Google News 公開節錄</span>' : ""}
        <span class="x-time">${dateText(row.display_time)}</span>
      </div>
      <div class="x-copy x-translation">${escapeHtml(row.translation || row.primary_text)}</div>
      ${row.primary_text ? `<div class="x-copy x-original">${escapeHtml(row.primary_text)}</div>` : ""}
      <div class="x-link-row"><a class="pill x-link" href="${escapeHtml(row.post_url)}"${externalAttrs(row.post_url)}>在 X 開啟 ${openIcon()}</a></div>
    </article>
  `;
}

function renderXPage() {
  mountMasthead({ active: "x" });
  app.className = "reading-shell";
  const shown = xRows.slice(0, pageState.xVisible);
  app.innerHTML = `
    ${sectionHeading({ id: "feed-title", icon: "", title: "X Posts", count: `目前顯示 ${shown.length} / ${xRows.length}` })}
    <div class="feed-stack">${shown.map(xCard).join("")}</div>
    ${pageState.xVisible < xRows.length ? `<div class="load-row"><button class="pill pill-ink" type="button" data-x-load-more>載入更多</button></div>` : ""}
  `;
}

function setupHomeSpy() {
  const links = [...document.querySelectorAll(".nav-pill[href^='#']")];
  const map = new Map(links.map((link) => [link.getAttribute("href").slice(1), link]));
  if (!("IntersectionObserver" in window)) return;
  const observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    links.forEach((link) => link.classList.remove("is-active"));
    const active = map.get(visible.target.id);
    if (active) active.classList.add("is-active");
  }, { rootMargin: "-18% 0px -62% 0px", threshold: [0.1, 0.25, 0.5] });
  map.forEach((_, id) => {
    const section = document.getElementById(id);
    if (section) observer.observe(section);
  });
}

document.addEventListener("click", (event) => {
  const archiveButton = event.target.closest("[data-archive-toggle]");
  if (archiveButton) {
    pageState.archiveOpen = !pageState.archiveOpen;
    document.querySelector(".archive-section").outerHTML = renderArchives();
    return;
  }

  const toggle = event.target.closest("[data-toggle]");
  if (toggle) {
    const id = toggle.dataset.toggle;
    pageState.expanded[id] = !pageState.expanded[id];
    if (page === "deep") renderFeedPage({ rows: deepRows, active: "analysis", title: "Deep Analysis", icon: "fa-feather-alt", kind: "analysis" });
    if (page === "podcast") renderFeedPage({ rows: podcastRows, active: "podcast", title: "Podcast Highlights", icon: "fa-microphone-alt", kind: "podcast" });
    return;
  }

  if (event.target.closest("[data-load-more]")) {
    pageState.visible += 12;
    if (page === "deep") renderFeedPage({ rows: deepRows, active: "analysis", title: "Deep Analysis", icon: "fa-feather-alt", kind: "analysis" });
    if (page === "podcast") renderFeedPage({ rows: podcastRows, active: "podcast", title: "Podcast Highlights", icon: "fa-microphone-alt", kind: "podcast" });
    return;
  }

  if (event.target.closest("[data-x-load-more]")) {
    pageState.xVisible += 30;
    renderXPage();
  }
});

if (page === "home") {
  renderHome();
} else if (page === "deep") {
  renderFeedPage({ rows: deepRows, active: "analysis", title: "Deep Analysis", icon: "fa-feather-alt", kind: "analysis" });
} else if (page === "podcast") {
  renderFeedPage({ rows: podcastRows, active: "podcast", title: "Podcast Highlights", icon: "fa-microphone-alt", kind: "podcast" });
} else if (page === "x") {
  renderXPage();
}
"""


def page_html(title: str, page: str, description: str) -> str:
    document_title = "Joyce's Daily" if page == "home" else f"{title} | Joyce's Daily"
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(document_title)}</title>
  <meta name="description" content="{html.escape(description)}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:ital,opsz,wght@0,6..96,500;0,6..96,600;1,6..96,500;1,6..96,600&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400;1,6..72,500&family=Schibsted+Grotesk:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
  <link rel="stylesheet" href="./assets/styles.css">
</head>
<body data-page="{html.escape(page)}">
  <main id="app"></main>
  <script type="module" src="./assets/app.js"></script>
</body>
</html>
"""


def build() -> None:
    deep_rows = load_deep_rows()
    podcast_rows = load_podcast_rows()
    x_rows = load_x_posts()
    news_data = load_news_data(deep_rows, podcast_rows)

    write_file(OUT_DIR / "assets" / "styles.css", STYLE_CSS.strip() + "\n")
    write_file(OUT_DIR / "assets" / "app.js", APP_JS.strip() + "\n")
    write_file(OUT_DIR / "data" / "news.js", f"export const newsData = {module_json(news_data)};\n")
    write_file(OUT_DIR / "data" / "deep-analysis.js", f"export const deepRows = {module_json(deep_rows)};\n")
    write_file(OUT_DIR / "data" / "podcast-highlights.js", f"export const podcastRows = {module_json(podcast_rows)};\n")
    write_file(OUT_DIR / "data" / "x-posts.js", f"export const xRows = {module_json(x_rows)};\n")
    write_file(OUT_DIR / "index.html", page_html("Joyce's Daily", "home", "Daily technology curation by Joyce."))
    write_file(OUT_DIR / "deep-analysis.html", page_html("Deep Analysis", "deep", "Deep Analysis archive."))
    write_file(OUT_DIR / "podcast-highlights.html", page_html("Podcast Highlights", "podcast", "Podcast Highlights archive."))
    write_file(OUT_DIR / "x-posts.html", page_html("X Posts", "x", "Translated public X posts."))
    print(
        "Site complete: "
        f"{len(news_data['techmeme'])} Techmeme, "
        f"{len(news_data['wsj'])} WSJ, "
        f"{len(deep_rows)} deep analysis, "
        f"{len(podcast_rows)} podcast, "
        f"{len(x_rows)} X posts."
    )


if __name__ == "__main__":
    build()
