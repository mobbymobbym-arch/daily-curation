#!/usr/bin/env python3

import argparse
import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path


ACCOUNT_COLORS = {
    "karpathy": "#3b82f6",
    "elonmusk": "#1e293b",
    "paulg": "#f59e0b",
    "claudeai": "#10b981",
    "openai": "#8b5cf6",
    "lexfridman": "#0f766e",
    "pmarca": "#c2410c",
    "sama": "#dc2626",
    "benthompson": "#0ea5e9",
    "andrewsharp": "#db2777",
    "davidsacks": "#a16207",
    "mingchikuo": "#2563eb",
    "stratechery": "#0f766e",
    "a16z": "#7c3aed",
    "brian_armstrong": "#2563eb",
}
INITIAL_VISIBLE_COUNT = 50
LOAD_MORE_COUNT = 25


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def translate_for_row(row, translations):
    if row["extraction_status"] == "text_extracted":
        return translations.get("success_translations", {}).get(row["post_url"])
    return translations.get("failed_candidate_translations", {}).get(row["google_news_url"])


def get_handle(row):
    if row.get("screen_name"):
        return row["screen_name"]
    query = row.get("query", "")
    if "/" in query:
        return query.rsplit("/", 1)[-1].lstrip("@")
    return query.lstrip("@")


def get_accent(handle):
    return ACCOUNT_COLORS.get((handle or "").lower(), "#111827")


def parse_row_datetime(row):
    value = row.get("rss_pub_date", "")
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


def format_display_time(row):
    parsed = parse_row_datetime(row)
    if parsed is None:
        return row.get("rss_pub_date", "")
    return parsed.strftime("%Y.%m.%d %H:%M")


def sort_rows(rows):
    def sort_key(row):
        parsed = parse_row_datetime(row)
        if parsed is None:
            return float("-inf")
        return parsed.timestamp()

    return sorted(rows, key=sort_key, reverse=True)


def detect_repost_label(row):
    text = (row.get("text") or "").strip()
    if not text:
        return None

    repost_match = re.match(r"^RT\s+@([A-Za-z0-9_]+):", text)
    if repost_match:
        return f"轉貼自 @{repost_match.group(1)}"

    return None


def prepare_rows(data, translations):
    prepared_rows = []

    for row in sort_rows(data["rows"]):
        handle = get_handle(row)
        prepared_rows.append(
            {
                "handle": handle,
                "accent": get_accent(handle),
                "display_time": format_display_time(row),
                "status": row["extraction_status"],
                "post_url": row.get("post_url"),
                "primary_text": row.get("text") or row.get("rss_title") or "",
                "translation": translate_for_row(row, translations) or "尚未提供翻譯。",
                "show_google_news_badge": row["extraction_status"] != "text_extracted" or bool(row.get("is_truncated")),
                "repost_label": detect_repost_label(row),
                "is_failed": row["extraction_status"] != "text_extracted",
            }
        )

    return prepared_rows


def build_html(rows, archive_generated_at):
    rows_json = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    visible_on_load = min(INITIAL_VISIBLE_COUNT, len(rows))

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Joyce's Daily Curation | X Posts</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root {{
            --bg-color: #fcf9f2;
            --primary-text: #1a1c20;
            --secondary-text: #64748b;
            --x-accent: #111827;
            --card-bg: #ffffff;
            --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            --shadow-hover: 0 20px 25px -5px rgba(0, 0, 0, 0.08), 0 10px 10px -5px rgba(0, 0, 0, 0.03);
            --line: rgba(0, 0, 0, 0.06);
        }}

        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg-color: #121210;
                --primary-text: #f8fafc;
                --secondary-text: #94a3b8;
                --card-bg: #1c1c1a;
                --shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
                --shadow-hover: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
                --line: rgba(255, 255, 255, 0.08);
            }}
        }}

        * {{ box-sizing: border-box; }}
        html {{ scroll-behavior: smooth; }}
        body {{ font-family: 'Inter', 'Noto Sans TC', -apple-system, sans-serif; background-color: var(--bg-color); color: var(--primary-text); margin: 0; line-height: 1.6; overflow-x: hidden; }}
        nav {{ position: sticky; top: 0; background: rgba(255, 255, 255, 0.7); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); z-index: 100; padding: 8px 0; border-bottom: 1px solid var(--line); }}
        @media (prefers-color-scheme: dark) {{ nav {{ background: rgba(15, 23, 42, 0.7); }} }}
        nav .nav-container {{ max-width: 1440px; margin: 0 auto; position: relative; padding: 0 54px 0 12px; }}
        nav .nav-links {{ display: flex; gap: 6px; row-gap: 6px; justify-content: center; flex-wrap: wrap; min-width: 0; padding: 0; }}
        nav .nav-links a {{ text-decoration: none; color: #1f2937; background: rgba(17, 24, 39, 0.08); border-color: rgba(17, 24, 39, 0.14); font-weight: 800; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.35px; transition: transform 0.2s, box-shadow 0.2s, background 0.2s, color 0.2s; white-space: nowrap; display: inline-flex; align-items: center; justify-content: center; min-height: 26px; padding: 5px 9px; border-radius: 999px; border: 1px solid transparent; line-height: 1; }}
        nav .nav-links a:hover {{ transform: translateY(-1px); box-shadow: 0 8px 16px rgba(15, 23, 42, 0.08); }}
        nav .nav-links a.nav-link-active,
        nav .nav-links a[aria-current="page"] {{ color: #ffffff; background: #111827; border-color: #111827; box-shadow: 0 8px 18px rgba(17, 24, 39, 0.18); }}
        @media (prefers-color-scheme: dark) {{
            nav .nav-links a {{ color: #e5e7eb; background: rgba(249, 250, 251, 0.1); border-color: rgba(249, 250, 251, 0.16); }}
            nav .nav-links a.nav-link-active,
            nav .nav-links a[aria-current="page"] {{ color: #111827; background: #f9fafb; border-color: #f9fafb; box-shadow: 0 8px 18px rgba(249, 250, 251, 0.12); }}
        }}
        .home-icon {{ position: fixed; top: calc(8px + env(safe-area-inset-top)); right: calc(12px + env(safe-area-inset-right)); z-index: 120; width: 30px; height: 30px; border-radius: 999px; color: var(--primary-text); background: rgba(255, 255, 255, 0.82); border: 1px solid rgba(17, 24, 39, 0.12); box-shadow: 0 8px 18px rgba(15, 23, 42, 0.12); font-size: 0.95rem; transition: transform 0.2s, box-shadow 0.2s; display: flex; align-items: center; justify-content: center; text-decoration: none; backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); }}
        .home-icon:hover {{ transform: translateY(-1px); box-shadow: 0 10px 22px rgba(15, 23, 42, 0.16); }}
        @media (prefers-color-scheme: dark) {{ .home-icon {{ color: #f9fafb; background: rgba(17, 24, 39, 0.78); border-color: rgba(249, 250, 251, 0.16); }} }}

        header {{ padding: clamp(64px, 10vw, 92px) 20px clamp(56px, 9vw, 84px); text-align: center; background: radial-gradient(circle at top left, #1e3a8a, #0f172a); color: white; position: relative; overflow: hidden; }}
        header::after {{ content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 100px; background: linear-gradient(to top, var(--bg-color), transparent); }}
        header h1 {{ font-size: clamp(2.2rem, 7vw, 3.5rem); font-weight: 900; margin: 0; letter-spacing: -1px; background: linear-gradient(to right, #fff, #94a3b8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .container {{ max-width: 1440px; margin: 0 auto; padding: clamp(24px, 4vw, 38px) clamp(14px, 3vw, 20px) calc(110px + env(safe-area-inset-bottom)); }}
        .section-header {{ max-width: 760px; margin: 0 auto 24px; display: flex; justify-content: space-between; align-items: flex-end; gap: 18px; flex-wrap: wrap; }}
        .section-header h2 {{ margin: 0; font-size: 1.8rem; font-weight: 800; letter-spacing: -0.5px; }}
        .section-meta {{ color: var(--secondary-text); font-weight: 700; font-size: 0.92rem; }}

        .feed-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
            max-width: 760px;
            margin: 0 auto;
            align-items: start;
        }}
        .x-card {{
            background: var(--card-bg);
            border-radius: 24px;
            padding: 24px;
            box-shadow: var(--shadow);
            border: 1px solid rgba(0,0,0,0.03);
            transition: transform 0.28s ease, box-shadow 0.28s ease;
            height: 100%;
        }}
        .x-card:hover {{ transform: translateY(-4px); box-shadow: var(--shadow-hover); }}
        .x-card-failed {{ background: linear-gradient(180deg, rgba(248,250,252,0.82), var(--card-bg)); }}

        .card-top {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 16px; flex-wrap: wrap; }}
        .handle-row {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
        .handle-chip {{ display: inline-flex; align-items: center; padding: 5px 11px; border-radius: 999px; color: white; font-size: 0.78rem; font-weight: 800; letter-spacing: 0.2px; }}
        .badge {{ display: inline-flex; align-items: center; padding: 5px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; }}
        .badge-warn {{ background: rgba(245, 158, 11, 0.16); color: #b45309; }}
        .badge-info {{ background: rgba(59, 130, 246, 0.12); color: #1d4ed8; }}
        .meta-time {{ margin-top: 10px; color: var(--secondary-text); font-size: 0.88rem; font-weight: 600; letter-spacing: 0.1px; }}
        .link-btn {{ text-decoration: none; font-weight: 800; font-size: 0.8rem; display: inline-flex; align-items: center; gap: 10px; transition: gap 0.3s; }}
        .link-btn:hover {{ gap: 15px; }}
        .link-btn-disabled {{ color: var(--secondary-text); cursor: default; }}
        .link-btn-disabled:hover {{ gap: 10px; }}

        .text-stack {{ background: rgba(248, 250, 252, 0.56); border: 1px solid var(--line); border-radius: 18px; padding: 22px; }}
        .panel-body {{ white-space: pre-wrap; font-size: 0.98rem; line-height: 1.75; overflow-wrap: anywhere; word-break: break-word; }}
        .translation-divider {{ height: 1px; background: var(--line); margin: 18px 0; }}
        .translation-body {{ color: #475569; }}

        .load-more-wrap {{ max-width: 760px; margin: 26px auto 0; display: flex; justify-content: center; }}
        .load-more-btn {{
            border: none;
            border-radius: 999px;
            padding: 14px 24px;
            font-size: 0.92rem;
            font-weight: 800;
            letter-spacing: 0.2px;
            color: white;
            background: linear-gradient(135deg, #0f172a, #1e3a8a);
            box-shadow: var(--shadow);
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
        }}
        .load-more-btn:hover {{ transform: translateY(-2px); box-shadow: var(--shadow-hover); }}
        .load-more-btn[hidden] {{ display: none; }}

        @media (max-width: 760px) {{
            nav {{ padding: 6px 0; }}
            nav .nav-container {{ padding: 0 48px 0 8px; }}
            nav .nav-links {{ gap: 5px; row-gap: 5px; }}
            nav .nav-links a {{ font-size: 0.62rem; min-height: 23px; padding: 4px 7px; letter-spacing: 0.2px; }}
            .home-icon {{ top: calc(6px + env(safe-area-inset-top)); right: calc(8px + env(safe-area-inset-right)); width: 28px; height: 28px; font-size: 0.88rem; }}
            .section-header {{
                margin-bottom: 18px;
                gap: 10px;
                align-items: flex-start;
            }}
            .section-header h2 {{ font-size: 1.45rem; }}
            .section-meta {{ font-size: 0.88rem; }}
            .feed-grid {{
                gap: 18px;
            }}
            .x-card {{
                padding: 18px;
                border-radius: 20px;
            }}
            .card-top {{
                gap: 12px;
                margin-bottom: 14px;
            }}
            .handle-chip,
            .badge {{
                font-size: 0.8rem;
            }}
            .meta-time {{
                margin-top: 8px;
                font-size: 0.86rem;
            }}
            .link-btn,
            .link-btn-disabled {{
                width: 100%;
                justify-content: center;
                padding: 12px 14px;
                border-radius: 14px;
                gap: 8px;
            }}
            .link-btn {{
                background: rgba(15, 23, 42, 0.06);
            }}
            .text-stack {{
                padding: 18px;
                border-radius: 16px;
            }}
            .panel-body {{
                font-size: 1rem;
                line-height: 1.82;
            }}
            .translation-divider {{
                margin: 16px 0;
            }}
            .load-more-wrap {{
                margin-top: 22px;
                padding-bottom: env(safe-area-inset-bottom);
            }}
            .load-more-btn {{
                width: min(100%, 420px);
                padding: 16px 20px;
                font-size: 1rem;
            }}
        }}

        @media (max-width: 480px) {{
            header {{
                padding-left: 16px;
                padding-right: 16px;
            }}
            .container {{
                padding-left: 12px;
                padding-right: 12px;
            }}
            .x-card {{
                padding: 16px;
            }}
            .text-stack {{
                padding: 16px;
            }}
        }}
    </style>
</head>
<body>
    <nav>
        <div class="nav-container">
            <div class="nav-links">
                <a class="nav-link" href="/daily-curation/#techmeme-section">Techmeme</a>
                <a class="nav-link" href="/daily-curation/#wsj-section">WSJ Tech</a>
                <a class="nav-link" href="/daily-curation/#analysis-section">Deep Analysis</a>
                <a class="nav-link" href="/daily-curation/#podcast-section">Podcast</a>
                <a class="nav-link nav-link-active" href="#candidate-feed" aria-current="page">X Posts</a>
            </div>
            <a href="/daily-curation/" class="home-icon"><i class="fas fa-home"></i></a>
        </div>
    </nav>

    <header id="top">
        <h1>Joyce's Daily</h1>
    </header>

    <div class="container">
        <div id="posts-feed" aria-hidden="true"></div>
        <section id="candidate-feed">
            <div class="section-header">
                <div><h2>X Posts</h2></div>
                <div class="section-meta" id="feed-count"></div>
            </div>

            <div class="feed-grid" id="feed-grid"></div>

            <div class="load-more-wrap">
                <button id="load-more-btn" class="load-more-btn">Read more</button>
            </div>
        </section>
    </div>

    <script id="x-post-rows" type="application/json">{rows_json}</script>
    <script>
        const INITIAL_VISIBLE_COUNT = {INITIAL_VISIBLE_COUNT};
        const LOAD_MORE_COUNT = {LOAD_MORE_COUNT};
        const allRows = JSON.parse(document.getElementById("x-post-rows").textContent);
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

        function buildBadgeHtml(row) {{
            const badges = [];
            if (row.show_google_news_badge) {{
                badges.push('<span class="badge badge-warn">Google News 公開節錄</span>');
            }}
            if (row.repost_label) {{
                badges.push(`<span class="badge badge-info">${{escapeHtml(row.repost_label)}}</span>`);
            }}
            return badges.join("");
        }}

        function buildLinkHtml(row) {{
            if (row.is_failed || !row.post_url) {{
                return '<span class="link-btn link-btn-disabled">未還原網址</span>';
            }}
            return `<a href="${{escapeHtml(row.post_url)}}" target="_blank" rel="noopener noreferrer" class="link-btn" style="color: ${{escapeHtml(row.accent)}};">Open on X &rarr;</a>`;
        }}

        function buildCardHtml(row) {{
            const failedClass = row.is_failed ? " x-card-failed" : "";
            return `
                <article class="x-card${{failedClass}}" style="border-top: 6px solid ${{escapeHtml(row.accent)}};">
                    <div class="card-top">
                        <div>
                            <div class="handle-row">
                                <span class="handle-chip" style="background: ${{escapeHtml(row.accent)}};">@${{escapeHtml(row.handle)}}</span>
                                ${{buildBadgeHtml(row)}}
                            </div>
                            <div class="meta-time">${{escapeHtml(row.display_time)}}</div>
                        </div>
                        ${{buildLinkHtml(row)}}
                    </div>
                    <div class="text-stack">
                        <div class="panel-body">${{escapeHtml(row.primary_text)}}</div>
                        <div class="translation-divider"></div>
                        <div class="panel-body translation-body">${{escapeHtml(row.translation)}}</div>
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

        loadMoreBtn.addEventListener("click", () => {{
            visibleCount = Math.min(visibleCount + LOAD_MORE_COUNT, allRows.length);
            renderFeed();
        }});

        renderFeed();
    </script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Render a Daily Curation style X tab preview page.")
    parser.add_argument("archive_json", help="Archive JSON for the cumulative X feed")
    parser.add_argument("translations_json", help="Translation mapping JSON")
    parser.add_argument("--output", required=True, help="Output HTML path")
    args = parser.parse_args()

    data = load_json(args.archive_json)
    translations = load_json(args.translations_json)
    prepared_rows = prepare_rows(data, translations)
    html_output = build_html(prepared_rows, data.get("generated_at", ""))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_output, encoding="utf-8")


if __name__ == "__main__":
    main()
