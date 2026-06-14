import json
import re
import os
import sys
from datetime import datetime

# Configuration
JSON_PATH = 'daily_news_temp.json'
HTML_PATH = 'index.html'

def load_data():
    if not os.path.exists(JSON_PATH):
        print(f"Error: {JSON_PATH} not found.")
        sys.exit(1)
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def external_link_attrs(url):
    if re.match(r'^https?://', str(url or ''), flags=re.I):
        return ' target="_blank" rel="noopener noreferrer"'
    return ''

def render_techmeme(items, fetch_date):
    html = f'''
            <!-- Techmeme Section -->
            <div id="techmeme-section" class="section-header" style="color: var(--techmeme-accent);">
                <i class="fas fa-bolt"></i>
                <h2><a href="https://www.techmeme.com/" target="_blank" rel="noopener noreferrer" style="color: inherit; text-decoration: none;">Techmeme Main Feed</a></h2>
                <p class="section-desc"><i class="far fa-calendar-alt"></i> {fetch_date}</p>
            </div>
            <div id="techmeme-grid" class="news-grid">'''
    
    for item in items:
        source_name = item.get('source') or item.get('media_source') or 'Read Story'
        url = item.get('url', '#')
        title_zh = item.get('title_zh') or ''
        title_en = item.get('title_en') or ''
        display_title = f"{title_zh}<br><small style='font-weight: normal; color: #666;'>{title_en}</small>" if title_zh else title_en
        
        html += f'''
                <div class="news-card" style="border-top: 6px solid var(--techmeme-accent);">
                    <div class="title-cn" style="font-weight: bold; margin-bottom: 8px; line-height: 1.4;">{display_title}</div>
                    <a href="{url}"{external_link_attrs(url)} class="link-btn" style="color: var(--techmeme-accent);">{source_name} &rarr;</a>
                </div>'''
    html += '</div>'
    return html

def render_wsj(items, fetch_date):
    html = f'''
            <!-- WSJ Section -->
            <div id="wsj-section" class="section-header" style="color: var(--wsj-accent);">
                <i class="fas fa-newspaper"></i>
                <h2><a href="https://www.wsj.com/tech?mod=nav_top_section" target="_blank" rel="noopener noreferrer" style="color: inherit; text-decoration: none;">WSJ Technology Top 10</a></h2>
                <p class="section-desc"><i class="far fa-calendar-alt"></i> {fetch_date}</p>
            </div>
            <div id="wsj-grid" class="news-grid">'''
    
    for item in items:
        url = item.get('url', '#')
        title_zh = item.get('title_zh') or ''
        title_en = item.get('title_en') or ''
        summary_zh = item.get('summary_zh') or ''
        display_title = f"{title_zh}<br><small style='font-weight: normal; color: #666;'>{title_en}</small>" if title_zh else title_en

        html += f'''
                <div class="news-card" style="border-top: 6px solid var(--wsj-accent);">
                    <div class="title-cn" style="font-weight: bold; margin-bottom: 8px; line-height: 1.4;">{display_title}</div>
                    <div class="summary-cn" style="font-size: 0.95rem; line-height: 1.6; color: #444; margin-top: 10px;">{summary_zh}</div>
                    <a href="{url}"{external_link_attrs(url)} class="link-btn" style="color: var(--wsj-accent);">WSJ &rarr;</a>
                </div>'''
    html += '</div>'
    return html


def teaser_text(value, limit=280):
    text = re.sub(r'<br\s*/?>', ' ', str(value or ''), flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit].rstrip() + ('...' if len(text) > limit else '')


def normalize_date(value):
    text = str(value or '').strip()
    match = re.search(r'(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})', text)
    if not match:
        return ''
    year, month, day = match.groups()
    return f'{int(year):04d}-{int(month):02d}-{int(day):02d}'


def analysis_sort_key(item):
    display_date = (
        item.get('article_date')
        or item.get('first_seen_date')
        or item.get('latest_seen_date')
        or ''
    )
    return (
        normalize_date(display_date),
        normalize_date(item.get('latest_seen_date')),
        normalize_date(item.get('first_seen_date')),
        str(item.get('source') or item.get('source_key') or ''),
        str(item.get('title') or item.get('title_zh') or ''),
    )


def render_deep_analysis(data):
    html = '''
            <!-- Deep Analysis Section -->
            <div id="analysis-section" class="section-header" style="color: var(--analysis-accent);">
                <i class="fas fa-feather-alt"></i>
                <h2>Deep Analysis</h2>
                <a href="/daily-curation/deep-analysis.html" class="link-btn section-view-all" style="color: var(--analysis-accent);">View all &rarr;</a>
            </div>
            <div id="deep-analysis-container" class="teaser-grid">'''
    
    analysis_items = []
    if isinstance(data, dict):
        for key, content in data.items():
            if isinstance(content, dict):
                # Check for analysis_zh or title to include newest format
                if 'title' in content or 'title_zh' in content or 'analysis_zh' in content:
                    content['source_key'] = key
                    analysis_items.append(content)

    analysis_items.sort(key=analysis_sort_key, reverse=True)

    for item in analysis_items[:3]:
        title = item.get('title') or item.get('title_zh') or 'Deep Analysis'
        source_name = item.get('source') or item.get('source_key') or 'Source'
        raw_summary = item.get('analysis_zh') or item.get('summary_zh') or item.get('summary') or item.get('content') or ''
        summary = teaser_text(raw_summary, 320)
        url = item.get('url') or item.get('link') or '#'
        article_date = item.get('article_date') or ''

        date_html = f'<div class="teaser-date">{article_date}</div>' if article_date else ''
        html += f'''
                <article class="teaser-card" style="--teaser-accent: var(--analysis-accent);">
                    <span class="teaser-chip">{source_name}</span>
                    <h3>{title}</h3>
                    {date_html}
                    <p class="teaser-summary">{summary}</p>
                    <div class="teaser-actions">
                        <a href="{url}"{external_link_attrs(url)} class="link-btn" style="color: var(--analysis-accent);">{source_name} &rarr;</a>
                        <a href="/daily-curation/deep-analysis.html" class="link-btn" style="color: var(--analysis-accent);">Read history &rarr;</a>
                    </div>
                </article>'''
    html += '</div>'
    return html

def main():
    print("Starting news render process...")
    data = load_data()
    fetch_date = data.get('fetch_date') or datetime.now().strftime('%Y-%m-%d')
    
    techmeme_data = data.get('techmeme', [])
    wsj_data = data.get('wsj', [])
    deep_analysis_data = data.get('deep_analysis', {})
    
    techmeme_html = render_techmeme(techmeme_data, fetch_date)
    wsj_html = render_wsj(wsj_data, fetch_date) 
    deep_analysis_html = render_deep_analysis(deep_analysis_data)
    
    full_news_html = f"            <!-- DAILY_NEWS_START -->\n{techmeme_html}\n{wsj_html}\n{deep_analysis_html}\n            <!-- DAILY_NEWS_END -->"
    
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    start_marker = "<!-- DAILY_NEWS_START -->"
    end_marker = "<!-- DAILY_NEWS_END -->"
    if start_marker not in content or end_marker not in content:
        print("❌ 錯誤：找不到 <!-- DAILY_NEWS_START --> 或 END 標記，為避免破壞版面已中斷渲染！")
        sys.exit(1)
        
    pattern = r'(<!-- DAILY_NEWS_START -->)([\s\S]*?)(<!-- DAILY_NEWS_END -->)'
    new_content = re.sub(pattern, full_news_html, content)
    
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print("Successfully restored full content and updated index.html.")

    # 💾 將每天的新聞也存一份到 archives/ 供更新目錄時抓取
    archive_dir = 'archives'
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
    
    archive_filename = f"{fetch_date}.html"
    archive_filepath = os.path.join(archive_dir, archive_filename)
    
    with open(archive_filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"📦 已將今日內容備份至：{archive_filepath}")

if __name__ == "__main__":
    main()
