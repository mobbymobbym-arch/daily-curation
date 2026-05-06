import argparse
import html
import json
import os
import re
import urllib.parse
from datetime import datetime
from pathlib import Path


ROOT = Path(".")
ARCHIVE_DIR = ROOT / "archives"
INDEX_FILE = ROOT / "index.html"

DEEP_FEED_JSON = ROOT / "deep_analysis_feed.json"
PODCAST_FEED_JSON = ROOT / "podcast_highlights_feed.json"
DEEP_PAGE = ROOT / "deep-analysis.html"
PODCAST_PAGE = ROOT / "podcast-highlights.html"


def read_text(path):
    return path.read_text(encoding="utf-8", errors="ignore")


def strip_tags(value):
    text = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def clean_url(url):
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(html.unescape(url).strip())
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        filtered = [
            (key, value)
            for key, value in query
            if key != "access_token" and not key.startswith("utm_")
        ]
        clean_query = urllib.parse.urlencode(filtered, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=clean_query)).rstrip("/")
    except Exception:
        return html.unescape(url).strip().rstrip("/")


def script_json(data):
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("<", "\\u003c").replace("</", "<\\/")


def extract_between(text, start_marker, end_marker):
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start)
    if end < 0:
        return ""
    return text[start:end]


def parse_deep_cards_from_html(content, snapshot_date, source_file):
    block = extract_between(content, '<div id="deep-analysis-container">', "<!-- DAILY_NEWS_END -->")
    if not block:
        return []

    marker = '<div class="news-card" style="border-top: 6px solid var(--analysis-accent);'
    chunks = block.split(marker)[1:]
    rows = []

    for chunk in chunks:
        card = marker + chunk
        source_match = re.search(r"<span[^>]*>(.*?)</span>", card, re.S)
        title_match = re.search(r"<h3[^>]*>(.*?)</h3>", card, re.S)
        content_match = re.search(
            r'<div class="analysis-content"[^>]*>\s*([\s\S]*?)\s*</div>\s*<div class="fade-mask"',
            card,
            re.S,
        )
        link_match = re.search(
            r"</button>\s*<a\s+href=\"([^\"]+)\"[\s\S]*?&rarr;</a>",
            card,
            re.S,
        )
        date_match = re.search(
            r'<div style="color: var\(--secondary-text\);[^"]*">([^<]+)</div>',
            card,
            re.S,
        )

        if not title_match or not content_match:
            continue

        source = strip_tags(source_match.group(1)) if source_match else "Deep Analysis"
        title = strip_tags(title_match.group(1))
        content_html = content_match.group(1).strip()
        url = html.unescape(link_match.group(1).strip()) if link_match else "#"
        article_date = strip_tags(date_match.group(1)) if date_match else ""

        key_url = clean_url(url)
        key = key_url if key_url and key_url != "#" else f"{source}|{title}"
        rows.append(
            {
                "key": key,
                "source": source,
                "title": title,
                "url": url,
                "clean_url": key_url,
                "article_date": article_date,
                "first_seen_date": snapshot_date,
                "latest_seen_date": snapshot_date,
                "source_file": source_file,
                "content_html": content_html,
                "preview": strip_tags(content_html)[:260],
            }
        )

    return rows


def render_deep_content_from_json(item):
    raw_summary = item.get("analysis_zh") or item.get("summary_zh") or item.get("summary") or item.get("content") or ""
    parts = [html.escape(str(raw_summary)).replace("\n", "<br><br>")]

    insights = item.get("insights", [])
    if insights and isinstance(insights, list):
        parts.append("<br><br><strong>關鍵洞察：</strong><br>")
        for index, insight in enumerate(insights, 1):
            if isinstance(insight, dict):
                topic = html.escape(str(insight.get("topic", "")))
                content = html.escape(str(insight.get("content_zh", insight.get("insight", ""))))
                parts.append(f"{index}. <strong>{topic}：</strong> {content}<br>")
            else:
                parts.append(f"{index}. {html.escape(str(insight))}<br>")

    supplemental_sources = item.get("supplemental_sources", [])
    if supplemental_sources and isinstance(supplemental_sources, list):
        parts.append("<br><br><strong>補充來源：</strong><br>")
        for source in supplemental_sources[:5]:
            if not isinstance(source, dict):
                continue
            source_title = html.escape(str(source.get("title") or source.get("url") or "Source"))
            source_url = html.escape(str(source.get("url") or "#"))
            parts.append(f'<a href="{source_url}" style="color: var(--accent); text-decoration: none;">{source_title}</a><br>')

    return "".join(parts)


def deep_rows_from_current_json():
    path = ROOT / "daily_news_temp.json"
    if not path.exists():
        return []

    try:
        data = json.loads(read_text(path))
    except Exception:
        return []

    fetch_date = data.get("fetch_date") or datetime.now().strftime("%Y-%m-%d")
    deep_data = data.get("deep_analysis") or {}
    if not isinstance(deep_data, dict):
        return []

    rows = []
    for source_key, item in deep_data.items():
        if not isinstance(item, dict):
            continue
        if not any(field in item for field in ("title", "title_zh", "analysis_zh", "summary_zh", "summary", "content")):
            continue

        source = str(item.get("source") or source_key or "Deep Analysis")
        title = str(item.get("title") or item.get("title_zh") or "Deep Analysis").strip()
        url = str(item.get("url") or item.get("link") or "#").strip()
        article_date = str(item.get("article_date") or "").strip()
        content_html = render_deep_content_from_json(item)
        key_url = clean_url(url)
        key = key_url if key_url and key_url != "#" else f"{source}|{title}"

        rows.append(
            {
                "key": key,
                "source": source,
                "title": title,
                "url": url,
                "clean_url": key_url,
                "article_date": article_date,
                "first_seen_date": fetch_date,
                "latest_seen_date": fetch_date,
                "source_file": "daily_news_temp.json",
                "content_html": content_html,
                "preview": strip_tags(content_html)[:260],
            }
        )
    return rows


def build_deep_feed():
    by_key = {}
    archive_files = sorted(ARCHIVE_DIR.glob("????-??-??.html"))
    for path in archive_files:
        snapshot_date = path.stem
        for row in parse_deep_cards_from_html(read_text(path), snapshot_date, f"archives/{path.name}"):
            existing = by_key.get(row["key"])
            if existing:
                existing["latest_seen_date"] = row["latest_seen_date"]
                if not existing.get("article_date") and row.get("article_date"):
                    existing["article_date"] = row["article_date"]
                for field in ("source", "title", "url", "clean_url", "source_file", "content_html", "preview"):
                    if row.get(field):
                        existing[field] = row[field]
                continue
            by_key[row["key"]] = row

    for row in deep_rows_from_current_json():
        existing = by_key.get(row["key"])
        if existing:
            existing["latest_seen_date"] = max(existing["latest_seen_date"], row["latest_seen_date"])
            for field in ("source", "title", "url", "clean_url", "source_file", "content_html", "preview"):
                if row.get(field):
                    existing[field] = row[field]
            continue
        by_key[row["key"]] = row

    if INDEX_FILE.exists():
        fetch_date = datetime.now().strftime("%Y-%m-%d")
        try:
            daily_data = json.loads(read_text(ROOT / "daily_news_temp.json"))
            fetch_date = daily_data.get("fetch_date") or fetch_date
        except Exception:
            pass
        for row in parse_deep_cards_from_html(read_text(INDEX_FILE), fetch_date, "index.html"):
            existing = by_key.get(row["key"])
            if existing:
                existing["latest_seen_date"] = max(existing["latest_seen_date"], row["latest_seen_date"])
                for field in ("source", "title", "url", "clean_url", "source_file", "content_html", "preview"):
                    if row.get(field):
                        existing[field] = row[field]
                continue
            by_key[row["key"]] = row

    rows = list(by_key.values())
    rows.sort(key=lambda item: (item.get("first_seen_date", ""), item.get("source", ""), item.get("title", "")), reverse=True)
    for index, row in enumerate(rows, 1):
        row["id"] = f"analysis-{index}"
        row.pop("key", None)
    return rows


def remove_last_closing_div(fragment):
    index = fragment.rfind("</div>")
    if index == -1:
        return fragment.strip()
    return (fragment[:index] + fragment[index + len("</div>") :]).strip()


def clean_podcast_show_name(value):
    value = strip_tags(value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s*-\s*Topic$", "", value, flags=re.I).strip()
    if not value:
        return ""
    if value.lower().startswith(("http://", "https://", "transcript for")):
        return ""
    if len(value) > 42:
        return ""
    return value


def infer_podcast_show_name(title, summary_html="", original_link="", fallback_label=""):
    fallback = clean_podcast_show_name(fallback_label)
    if fallback:
        return fallback

    title = strip_tags(title)
    summary = strip_tags(summary_html)
    combined = f"{title} {summary}"

    known_patterns = [
        (r"Dwarkesh Podcast|主持人\s*Dwarkesh|Dwarkesh Patel", "Dwarkesh"),
        (r"Lex Fridman Podcast|lexfridman\.com", "Lex Fridman"),
        (r"The a16z Show", "a16z Show"),
        (r"All-In Podcast", "All-In"),
        (r"Invest Like the Best", "Invest Like the Best"),
        (r"Business Breakdowns", "Business Breakdowns"),
        (r"This Week in AI", "This Week in AI"),
        (r"Diet TBPN|TBPN", "TBPN"),
        (r"Core Memory", "Core Memory"),
        (r"Lenny Rachitsky|Lenny專訪|Lenny's Podcast", "Lenny's Podcast"),
        (r"Ashlee Vance", "Ashlee Vance"),
        (r"Ti Morse", "Ti Morse"),
        (r"Notion CEO|Notion 執行長", "Notion"),
    ]
    for pattern, label in known_patterns:
        if re.search(pattern, combined, re.I):
            return label

    if ":" in title:
        prefix = title.split(":", 1)[0].strip()
        if 2 <= len(prefix) <= 28 and not prefix.lower().startswith("transcript for"):
            return prefix

    if "|" in title:
        segments = [part.strip() for part in title.split("|") if part.strip()]
        for segment in reversed(segments):
            if re.search(r"(Podcast|Show|Memory|TBPN|a16z|Lenny|Dwarkesh|Fridman)", segment, re.I):
                return re.sub(r"\s+#\d+.*$", "", segment).strip()

    host_match = re.search(r"主持人\s*([^，；。:：]+)", summary)
    if host_match:
        host = host_match.group(1).strip()
        if host and not re.search(r"系統|我|群", host):
            return host[:28]

    domain = urllib.parse.urlparse(original_link or "").netloc.lower()
    if "spotify" in domain:
        return "Spotify"
    if "podcasts.apple" in domain:
        return "Apple Podcasts"
    if "youtube" in domain or "youtu.be" in domain:
        return "YouTube"
    return "Podcast"


def parse_podcast_cards_from_html(content, date_str, source_file):
    block = extract_between(content, "<!-- PODCAST_HIGHLIGHTS_START -->", "<!-- PODCAST_HIGHLIGHTS_END -->")
    if not block:
        return []

    marker = '<div class="podcast-highlight-card"'
    chunks = block.split(marker)[1:]
    rows = []

    for chunk in chunks:
        card = marker + chunk
        title_match = re.search(r"<h2[^>]*>(.*?)</h2>", card, re.S)
        summary_match = re.search(r"<p[^>]*>(.*?)</p>", card, re.S)
        link_match = re.search(r'<a href="([^"]+)"[^>]*>[\s\S]*?收聽原始節目[\s\S]*?</a>', card, re.S)
        details_match = re.search(
            r'<div id="podcast-chapters-content-[^"]+"[^>]*>([\s\S]*?)\n\s*<a href=',
            card,
            re.S,
        )

        if not title_match:
            continue

        title = strip_tags(title_match.group(1))
        summary_html = summary_match.group(1).strip() if summary_match else ""
        original_link = html.unescape(link_match.group(1).strip()) if link_match else "#"
        details_html = remove_last_closing_div(details_match.group(1)) if details_match else ""
        key_url = clean_url(original_link)
        key = key_url if key_url and key_url != "#" else f"{date_str}|{title}"

        rows.append(
            {
                "key": key,
                "title": title,
                "show_name": infer_podcast_show_name(title, summary_html, original_link),
                "date": date_str,
                "generated_at": "",
                "original_link": original_link,
                "source_file": source_file,
                "summary_html": summary_html,
                "details_html": details_html,
                "preview": strip_tags(summary_html)[:240],
            }
        )
    return rows


def render_podcast_details_from_json(item):
    chapters = item.get("chapters") or []
    parts = []
    for chapter in chapters:
        timestamp = html.escape(str(chapter.get("timestamp", "")))
        title = html.escape(str(chapter.get("title") or chapter.get("chapter_title") or "未命名章節"))
        content = html.escape(str(chapter.get("content", ""))).replace("\n", "<br>")
        quote = str(chapter.get("quote", "")).strip()
        parts.append('<div class="podcast-chapter">')
        parts.append(f'<h3><span>{timestamp}</span>{title}</h3>')
        parts.append(f"<p>{content}</p>")
        if quote:
            parts.append(f"<blockquote>{html.escape(quote)}</blockquote>")
        parts.append("</div>")
    return "\n".join(parts)


def podcast_rows_from_current_json():
    path = ROOT / "podcast_data.json"
    if not path.exists():
        return []

    try:
        data = json.loads(read_text(path))
    except Exception:
        return []

    date_str = data.get("date") or datetime.now().strftime("%Y-%m-%d")
    rows = []
    for item in data.get("items", []):
        title = str(item.get("title") or "Podcast Highlights").strip()
        original_link = str(item.get("original_link") or "#").strip()
        key_url = clean_url(original_link)
        key = key_url if key_url and key_url != "#" else f"{date_str}|{title}"
        summary = str(item.get("summary") or "").strip()
        rows.append(
            {
                "key": key,
                "title": title,
                "show_name": infer_podcast_show_name(
                    title,
                    html.escape(summary).replace("\n", "<br>"),
                    original_link,
                    item.get("show_name")
                    or item.get("podcast_show")
                    or item.get("channel")
                    or item.get("uploader")
                    or "",
                ),
                "date": date_str,
                "generated_at": str(item.get("generated_at") or ""),
                "original_link": original_link,
                "source_file": "podcast_data.json",
                "summary_html": html.escape(summary).replace("\n", "<br>"),
                "details_html": render_podcast_details_from_json(item),
                "preview": strip_tags(summary)[:240],
            }
        )
    return rows


def podcast_rows_from_existing_feed():
    if not PODCAST_FEED_JSON.exists():
        return []

    try:
        data = json.loads(read_text(PODCAST_FEED_JSON))
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "Podcast Highlights").strip()
        original_link = str(item.get("original_link") or item.get("url") or "#").strip()
        date_str = str(item.get("date") or item.get("first_seen_date") or "").strip()
        key_url = clean_url(original_link)
        key = key_url if key_url and key_url != "#" else f"{date_str}|{title}"
        row = dict(item)
        row["key"] = key
        row["title"] = title
        row["date"] = date_str
        row["original_link"] = original_link
        row["show_name"] = infer_podcast_show_name(
            title,
            str(row.get("summary_html") or row.get("preview") or ""),
            original_link,
            row.get("show_name") or "",
        )
        row.pop("id", None)
        rows.append(row)
    return rows


def build_podcast_feed():
    by_key = {}
    for row in podcast_rows_from_existing_feed():
        by_key[row["key"]] = row

    for path in sorted(ARCHIVE_DIR.glob("podcast-????-??-??.html")):
        date_match = re.search(r"podcast-(\d{4}-\d{2}-\d{2})", path.name)
        date_str = date_match.group(1) if date_match else path.stem
        for row in parse_podcast_cards_from_html(read_text(path), date_str, f"archives/{path.name}"):
            by_key.setdefault(row["key"], row)

    for row in podcast_rows_from_current_json():
        by_key[row["key"]] = row

    rows = list(by_key.values())
    rows.sort(key=lambda item: (item.get("date", ""), item.get("generated_at", ""), item.get("title", "")), reverse=True)
    for index, row in enumerate(rows, 1):
        row["id"] = f"podcast-{index}"
        row.pop("key", None)
    return rows


def page_nav(active):
    items = [
        ("Techmeme", "/daily-curation/#techmeme-section", "techmeme"),
        ("WSJ Tech", "/daily-curation/#wsj-section", "wsj"),
        ("Deep Analysis", "/daily-curation/deep-analysis.html", "deep"),
        ("Podcast", "/daily-curation/podcast-highlights.html", "podcast"),
        ("X Posts", "/daily-curation/x-posts.html", "x"),
    ]
    links = []
    for label, href, key in items:
        active_attrs = ' class="nav-link nav-link-active" aria-current="page"' if key == active else ' class="nav-link"'
        links.append(f'<a{active_attrs} href="{href}">{label}</a>')
    return "\n                ".join(links)


def page_styles(accent, accent_dark):
    return f"""
        :root {{
            --bg-color: #fcf9f2;
            --primary-text: #1a1c20;
            --secondary-text: #64748b;
            --accent: {accent};
            --accent-dark: {accent_dark};
            --card-bg: #ffffff;
            --line: rgba(15, 23, 42, 0.08);
            --soft: rgba(248, 250, 252, 0.72);
            --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            --shadow-hover: 0 20px 25px -5px rgba(0, 0, 0, 0.08), 0 10px 10px -5px rgba(0, 0, 0, 0.03);
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg-color: #121210;
                --primary-text: #f8fafc;
                --secondary-text: #94a3b8;
                --card-bg: #1c1c1a;
                --line: rgba(255, 255, 255, 0.09);
                --soft: rgba(15, 23, 42, 0.42);
                --shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
                --shadow-hover: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
            }}
        }}
        * {{ box-sizing: border-box; }}
        html {{ scroll-behavior: smooth; }}
        body {{
            font-family: 'Inter', 'Noto Sans TC', -apple-system, sans-serif;
            background: var(--bg-color);
            color: var(--primary-text);
            margin: 0;
            line-height: 1.7;
            overflow-x: hidden;
        }}
        nav {{
            position: sticky;
            top: 0;
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            z-index: 100;
            padding: 8px 0;
            border-bottom: 1px solid var(--line);
        }}
        @media (prefers-color-scheme: dark) {{ nav {{ background: rgba(15, 23, 42, 0.7); }} }}
        nav .nav-container {{ max-width: 1440px; margin: 0 auto; position: relative; padding: 0 54px 0 12px; }}
        nav .nav-links {{ display: flex; gap: 6px; row-gap: 6px; justify-content: center; flex-wrap: wrap; min-width: 0; padding: 0; }}
        nav .nav-links a {{
            text-decoration: none;
            color: #1f2937;
            background: rgba(17, 24, 39, 0.08);
            border-color: rgba(17, 24, 39, 0.14);
            font-weight: 800;
            font-size: 0.68rem;
            text-transform: uppercase;
            letter-spacing: 0.35px;
            transition: transform 0.2s, box-shadow 0.2s, background 0.2s, color 0.2s;
            white-space: nowrap;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 26px;
            padding: 5px 9px;
            border-radius: 999px;
            border: 1px solid transparent;
            line-height: 1;
        }}
        nav .nav-links a:hover {{ transform: translateY(-1px); box-shadow: 0 8px 16px rgba(15, 23, 42, 0.08); }}
        nav .nav-links a.nav-link-active,
        nav .nav-links a[aria-current="page"] {{ color: #ffffff; background: #111827; border-color: #111827; box-shadow: 0 8px 18px rgba(17, 24, 39, 0.18); }}
        @media (prefers-color-scheme: dark) {{
            nav .nav-links a {{ color: #e5e7eb; background: rgba(249, 250, 251, 0.1); border-color: rgba(249, 250, 251, 0.16); }}
            nav .nav-links a.nav-link-active,
            nav .nav-links a[aria-current="page"] {{ color: #111827; background: #f9fafb; border-color: #f9fafb; box-shadow: 0 8px 18px rgba(249, 250, 251, 0.12); }}
        }}
        .home-icon {{
            position: fixed;
            top: calc(8px + env(safe-area-inset-top));
            right: calc(12px + env(safe-area-inset-right));
            z-index: 120;
            width: 30px;
            height: 30px;
            border-radius: 999px;
            color: var(--primary-text);
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(17, 24, 39, 0.12);
            box-shadow: 0 8px 18px rgba(15, 23, 42, 0.12);
            font-size: 0.95rem;
            transition: transform 0.2s, box-shadow 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
        }}
        .home-icon:hover {{ transform: translateY(-1px); box-shadow: 0 10px 22px rgba(15, 23, 42, 0.16); }}
        @media (prefers-color-scheme: dark) {{ .home-icon {{ color: #f9fafb; background: rgba(17, 24, 39, 0.78); border-color: rgba(249, 250, 251, 0.16); }} }}
        header {{
            padding: clamp(64px, 10vw, 92px) 20px clamp(52px, 8vw, 76px);
            text-align: center;
            background: radial-gradient(circle at top left, var(--accent-dark), #0f172a);
            color: white;
            position: relative;
            overflow: hidden;
        }}
        header::after {{ content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 90px; background: linear-gradient(to top, var(--bg-color), transparent); }}
        header h1 {{
            position: relative;
            z-index: 1;
            font-size: 3.4rem;
            font-weight: 900;
            margin: 0;
            letter-spacing: 0;
            line-height: 1.08;
            overflow-wrap: anywhere;
            word-break: break-word;
        }}
        .container {{ max-width: 1440px; margin: 0 auto; padding: clamp(24px, 4vw, 38px) clamp(14px, 3vw, 22px) calc(110px + env(safe-area-inset-bottom)); }}
        .section-header {{
            max-width: 760px;
            margin: 0 auto 24px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            gap: 18px;
            flex-wrap: wrap;
        }}
        .section-header h2 {{ margin: 0; font-size: 1.8rem; font-weight: 850; letter-spacing: 0; }}
        .section-meta {{ color: var(--secondary-text); font-weight: 750; font-size: 0.92rem; }}
        .masonry-feed {{
            display: grid;
            grid-template-columns: minmax(0, 1fr);
            gap: 22px;
            max-width: 760px;
            margin: 0 auto;
        }}
        .feed-card {{
            display: block;
            width: 100%;
            margin: 0;
            break-inside: avoid;
            background: var(--card-bg);
            border-radius: 18px;
            padding: 24px;
            box-shadow: var(--shadow);
            border: 1px solid rgba(0,0,0,0.03);
            border-top: 6px solid var(--accent);
            transition: transform 0.28s ease, box-shadow 0.28s ease;
        }}
        .feed-card:hover {{ transform: translateY(-3px); box-shadow: var(--shadow-hover); }}
        .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; }}
        .source-chip {{
            display: inline-flex;
            align-items: center;
            padding: 5px 10px;
            border-radius: 999px;
            color: white;
            background: var(--accent);
            font-size: 0.74rem;
            font-weight: 850;
            line-height: 1;
        }}
        .card-date {{ color: var(--secondary-text); font-size: 0.82rem; font-weight: 700; margin-top: 8px; }}
        .feed-card h3 {{ font-size: 1.22rem; line-height: 1.38; margin: 0 0 14px; letter-spacing: 0; overflow-wrap: anywhere; word-break: break-word; }}
        .summary-text {{ color: #475569; font-size: 0.96rem; line-height: 1.72; }}
        @media (prefers-color-scheme: dark) {{ .summary-text {{ color: #cbd5e1; }} }}
        .content-shell {{
            position: relative;
            max-height: 260px;
            overflow: hidden;
            transition: max-height 0.35s ease;
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid var(--line);
        }}
        .content-shell.expanded {{ max-height: none; }}
        .content-shell::after {{
            content: '';
            position: absolute;
            left: 0;
            right: 0;
            bottom: 0;
            height: 76px;
            pointer-events: none;
            background: linear-gradient(transparent, var(--card-bg));
            opacity: 1;
            transition: opacity 0.2s ease;
        }}
        .content-shell.expanded::after {{ opacity: 0; }}
        .content-body {{ line-height: 1.82; color: var(--primary-text); overflow-wrap: anywhere; word-break: break-word; }}
        .content-body a {{ color: var(--accent-dark); text-decoration: none; font-weight: 750; }}
        .content-body a:hover {{ text-decoration: underline; }}
        .toggle-btn, .source-link, .load-more-btn {{
            border: none;
            border-radius: 999px;
            font-size: 0.86rem;
            font-weight: 850;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            min-height: 38px;
            padding: 9px 15px;
        }}
        .toggle-btn {{ color: var(--accent-dark); background: rgba(16, 185, 129, 0.1); margin-top: 14px; }}
        .source-link {{ color: var(--accent-dark); background: transparent; padding-left: 0; padding-right: 0; }}
        .card-actions {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 12px; }}
        .load-more-wrap {{ max-width: 760px; margin: 28px auto 0; display: flex; justify-content: center; }}
        .load-more-btn {{
            color: white;
            background: linear-gradient(135deg, var(--accent-dark), #0f172a);
            box-shadow: var(--shadow);
            padding: 14px 24px;
        }}
        .load-more-btn:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-hover); }}
        .load-more-btn[hidden] {{ display: none; }}
        .podcast-chapter {{ margin-bottom: 22px; }}
        .podcast-chapter h3 {{ font-size: 1.05rem; margin: 0 0 10px; }}
        .podcast-chapter h3 span {{
            display: inline-flex;
            margin-right: 8px;
            color: var(--accent-dark);
            background: rgba(139, 92, 246, 0.11);
            padding: 2px 8px;
            border-radius: 8px;
            font-size: 0.86rem;
        }}
        blockquote {{
            margin: 14px 0;
            padding: 12px 16px;
            border-left: 4px solid var(--accent);
            background: var(--soft);
            color: #475569;
            font-style: italic;
        }}
        @media (max-width: 720px) {{
            nav {{ padding: 6px 0; }}
            nav .nav-container {{ padding: 0 48px 0 8px; }}
            nav .nav-links {{ gap: 5px; row-gap: 5px; }}
            nav .nav-links a {{ font-size: 0.62rem; min-height: 23px; padding: 4px 7px; letter-spacing: 0.2px; }}
            .home-icon {{ top: calc(6px + env(safe-area-inset-top)); right: calc(8px + env(safe-area-inset-right)); width: 28px; height: 28px; font-size: 0.88rem; }}
            header h1 {{ font-size: 1.55rem; }}
            .feed-card {{ border-radius: 16px; padding: 18px; }}
            .section-header {{ align-items: flex-start; gap: 10px; }}
            .section-header h2 {{ font-size: 1.48rem; }}
            .card-top {{ display: block; }}
            .content-shell {{ max-height: 300px; }}
            .toggle-btn, .source-link {{ width: 100%; }}
            .card-actions {{ align-items: stretch; }}
            .load-more-btn {{ width: min(100%, 420px); }}
        }}
        @media (max-width: 360px) {{
            header h1 {{ font-size: 1.35rem; }}
        }}
    """


def render_page(title, active, data, body_kind, accent, accent_dark, initial_count, load_count):
    data_json = script_json(data)
    styles = page_styles(accent, accent_dark)
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Joyce's Daily Curation | {html.escape(title)}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>{styles}</style>
</head>
<body>
    <nav>
        <div class="nav-container">
            <div class="nav-links">
                {page_nav(active)}
            </div>
            <a href="/daily-curation/" class="home-icon"><i class="fas fa-home"></i></a>
        </div>
    </nav>
    <header id="top">
        <h1>Joyce's Daily</h1>
    </header>
    <div class="container">
        <section id="archive-feed">
            <div class="section-header">
                <div><h2>{html.escape(title)}</h2></div>
                <div class="section-meta" id="feed-count"></div>
            </div>
            <div class="masonry-feed" id="feed-grid"></div>
            <div class="load-more-wrap">
                <button id="load-more-btn" class="load-more-btn">Read more</button>
            </div>
        </section>
    </div>
    <script id="feed-rows" type="application/json">{data_json}</script>
    <script>
        const INITIAL_VISIBLE_COUNT = {initial_count};
        const LOAD_MORE_COUNT = {load_count};
        const FEED_KIND = "{body_kind}";
        const allRows = JSON.parse(document.getElementById("feed-rows").textContent);
        const grid = document.getElementById("feed-grid");
        const loadMoreBtn = document.getElementById("load-more-btn");
        const feedCount = document.getElementById("feed-count");
        let visibleCount = Math.min(INITIAL_VISIBLE_COUNT, allRows.length);

        function escapeHtml(value) {{
            return String(value ?? "")
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#39;");
        }}

        function sourceLabel(row) {{
            if (FEED_KIND === "podcast") return row.show_name || "Podcast";
            return row.source || "Deep Analysis";
        }}

        function rowDate(row) {{
            if (FEED_KIND === "podcast") return row.date || "";
            return row.article_date || row.first_seen_date || "";
        }}

        function buildSourceLink(row) {{
            const url = row.url || row.original_link;
            if (!url || url === "#") return "";
            const label = FEED_KIND === "podcast" ? "Listen" : "Original";
            return `<a href="${{escapeHtml(url)}}" class="source-link" target="_blank" rel="noopener">${{label}} &rarr;</a>`;
        }}

        function buildContent(row) {{
            if (FEED_KIND === "podcast") {{
                const details = row.details_html || "";
                return `
                    <div class="summary-text">${{row.summary_html || escapeHtml(row.preview || "")}}</div>
                    ${{details ? `<div class="content-shell" id="${{escapeHtml(row.id)}}-content"><div class="content-body">${{details}}</div></div>` : ""}}
                `;
            }}
            return `
                <div class="content-shell" id="${{escapeHtml(row.id)}}-content"><div class="content-body">${{row.content_html || ""}}</div></div>
            `;
        }}

        function buildToggle(row) {{
            const hasDetails = FEED_KIND === "podcast" ? Boolean(row.details_html) : Boolean(row.content_html);
            if (!hasDetails) return "";
            return `<button class="toggle-btn" data-toggle="${{escapeHtml(row.id)}}-content">展開全文</button>`;
        }}

        function buildCardHtml(row) {{
            return `
                <article class="feed-card">
                    <div class="card-top">
                        <div>
                            <span class="source-chip">${{escapeHtml(sourceLabel(row))}}</span>
                            <div class="card-date">${{escapeHtml(rowDate(row))}}</div>
                        </div>
                    </div>
                    <h3>${{escapeHtml(row.title)}}</h3>
                    ${{buildContent(row)}}
                    <div class="card-actions">
                        ${{buildToggle(row)}}
                        ${{buildSourceLink(row)}}
                    </div>
                </article>
            `;
        }}

        function renderFeed() {{
            const visibleRows = allRows.slice(0, visibleCount);
            grid.innerHTML = visibleRows.map(buildCardHtml).join("");
            feedCount.textContent = `目前顯示 ${{visibleRows.length}} / ${{allRows.length}}`;
            loadMoreBtn.hidden = visibleCount >= allRows.length;
        }}

        grid.addEventListener("click", (event) => {{
            const button = event.target.closest("[data-toggle]");
            if (!button) return;
            const target = document.getElementById(button.dataset.toggle);
            if (!target) return;
            target.classList.toggle("expanded");
            button.textContent = target.classList.contains("expanded") ? "收合全文" : "展開全文";
        }});

        loadMoreBtn.addEventListener("click", () => {{
            visibleCount = Math.min(visibleCount + LOAD_MORE_COUNT, allRows.length);
            renderFeed();
        }});

        renderFeed();
    </script>
</body>
</html>
"""


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_deep_outputs():
    deep_rows = build_deep_feed()
    write_json(DEEP_FEED_JSON, deep_rows)
    DEEP_PAGE.write_text(
        render_page(
            "Deep Analysis",
            "deep",
            deep_rows,
            "deep",
            "#10b981",
            "#047857",
            12,
            12,
        ),
        encoding="utf-8",
    )
    print(f"✅ Deep Analysis feed: {len(deep_rows)} items -> {DEEP_PAGE}")
    return deep_rows


def build_podcast_outputs():
    podcast_rows = build_podcast_feed()
    write_json(PODCAST_FEED_JSON, podcast_rows)
    PODCAST_PAGE.write_text(
        render_page(
            "Podcast Highlights",
            "podcast",
            podcast_rows,
            "podcast",
            "#8b5cf6",
            "#6d28d9",
            10,
            10,
        ),
        encoding="utf-8",
    )
    print(f"✅ Podcast Highlights feed: {len(podcast_rows)} items -> {PODCAST_PAGE}")
    return podcast_rows


def main(only="all"):
    if only in ("all", "deep"):
        build_deep_outputs()
    if only in ("all", "podcast"):
        build_podcast_outputs()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Daily Curation section feeds and pages.")
    parser.add_argument(
        "--only",
        choices=("all", "deep", "podcast"),
        default="all",
        help="Limit output to one section. Defaults to rebuilding every section page.",
    )
    args = parser.parse_args()
    main(args.only)
