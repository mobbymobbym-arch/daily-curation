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

def render_techmeme(items, fetch_date):
    html = f'''
            <!-- Techmeme Section -->
            <div id="techmeme-section" class="section-header" style="color: var(--techmeme-accent);">
                <i class="fas fa-bolt"></i>
                <h2>Techmeme Main Feed</h2>
                <p class="section-desc"><i class="far fa-calendar-alt"></i> {fetch_date}</p>
            </div>
            <div id="techmeme-grid" class="news-grid">'''
    
    for item in items:
        source_name = item.get('source') or item.get('media_source') or 'Read Story'
        title_zh = item.get('title_zh') or ''
        title_en = item.get('title_en') or ''
        display_title = f"{title_zh}<br><small style='font-weight: normal; color: #666;'>{title_en}</small>" if title_zh else title_en
        
        html += f'''
                <div class="news-card" style="border-top: 6px solid var(--techmeme-accent);">
                    <div class="title-cn" style="font-weight: bold; margin-bottom: 8px; line-height: 1.4;">{display_title}</div>
                    <a href="{item.get('url', '#')}" class="link-btn" style="color: var(--techmeme-accent);">{source_name} &rarr;</a>
                </div>'''
    html += '</div>'
    return html

def render_wsj(items, fetch_date):
    html = f'''
            <!-- WSJ Section -->
            <div id="wsj-section" class="section-header" style="color: var(--wsj-accent);">
                <i class="fas fa-newspaper"></i>
                <h2>WSJ Technology Top 10</h2>
                <p class="section-desc"><i class="far fa-calendar-alt"></i> {fetch_date}</p>
            </div>
            <div id="wsj-grid" class="news-grid">'''
    
    for item in items:
        title_zh = item.get('title_zh') or ''
        title_en = item.get('title_en') or ''
        summary_zh = item.get('summary_zh') or ''
        display_title = f"{title_zh}<br><small style='font-weight: normal; color: #666;'>{title_en}</small>" if title_zh else title_en

        html += f'''
                <div class="news-card" style="border-top: 6px solid var(--wsj-accent);">
                    <div class="title-cn" style="font-weight: bold; margin-bottom: 8px; line-height: 1.4;">{display_title}</div>
                    <div class="summary-cn" style="font-size: 0.95rem; line-height: 1.6; color: #444; margin-top: 10px;">{summary_zh}</div>
                    <a href="{item.get('url', '#')}" class="link-btn" style="color: var(--wsj-accent);">WSJ &rarr;</a>
                </div>'''
    html += '</div>'
    return html

def render_deep_analysis(data):
    html = '''
            <!-- Deep Analysis Section -->
            <div id="analysis-section" class="section-header" style="color: var(--analysis-accent);">
                <i class="fas fa-feather-alt"></i>
                <h2>Deep Analysis</h2>
                <p class="section-desc">Daily Intelligence</p>
            </div>
            <div id="deep-analysis-container">'''
    
    analysis_items = []
    if isinstance(data, dict):
        priority_keys = ['Stratechery', 'Dwarkesh', 'stratechery', 'dwarkesh']
        processed_keys = set()
        for key in priority_keys:
            if key in data and data[key]:
                item = data[key]
                item['source_key'] = key
                analysis_items.append(item)
                processed_keys.add(key)
        for key, content in data.items():
            if key not in processed_keys and isinstance(content, dict):
                # Check for analysis_zh or title to include newest format
                if 'title' in content or 'title_zh' in content or 'analysis_zh' in content:
                    content['source_key'] = key
                    analysis_items.append(content)

    for i, item in enumerate(analysis_items):
        toggle_id = f"analysis-toggle-{i}"
        title = item.get('title') or item.get('title_zh') or 'Deep Analysis'
        source_name = item.get('source') or item.get('source_key') or 'Source'
        raw_summary = item.get('analysis_zh') or item.get('summary_zh') or item.get('summary') or item.get('content') or ''
        summary = str(raw_summary).replace('\\n', '<br><br>').replace('\n', '<br><br>')
        url = item.get('url') or item.get('link') or '#'
        
        insights_html = ""
        insights = item.get('insights', [])
        if insights and isinstance(insights, list):
            insights_html = "<br><br><strong>關鍵洞察：</strong><br>"
            for idx, insight in enumerate(insights):
                if isinstance(insight, dict):
                    topic = insight.get('topic', '')
                    content = insight.get('content_zh', insight.get('insight', ''))
                    insights_html += f"{idx+1}. <strong>{topic}：</strong> {content}<br>"
                else:
                    insights_html += f"{idx+1}. {insight}<br>"

        full_content = summary + insights_html
        html += f'''
                <div class="news-card" style="border-top: 6px solid var(--analysis-accent); margin-bottom: 40px; width: 100%; box-sizing: border-box;">
                    <span style="display: inline-block; background: var(--analysis-accent); color: white; font-size: 0.75rem; font-weight: 700; padding: 3px 10px; border-radius: 4px; margin-bottom: 12px; letter-spacing: 0.5px;">{source_name}</span>
                    <h3 style="font-size: 1.6rem; font-weight: bold; margin-top: 0;">{title}</h3>
                    <div class="expand-wrapper" id="{toggle_id}">
                        <div class="analysis-content" style="margin-top: 20px; line-height: 1.8;">
                            {full_content}
                        </div>
                        <div class="fade-mask"></div>
                    </div>
                    <button class="toggle-btn" onclick="toggleAnalysis('{toggle_id}')">展開全文 👀</button>
                    <a href="{url}" style="color: var(--analysis-accent); font-weight: bold; text-decoration: none; display: block; margin-top: 15px;">{source_name} &rarr;</a>
                </div>'''
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
    
    full_news_html = f"\n            <!-- DAILY_NEWS_START -->\n{techmeme_html}\n{wsj_html}\n{deep_analysis_html}\n            <!-- DAILY_NEWS_END -->"
    
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
