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

def render_techmeme(items):
    html = ""
    # Header
    html += f'''
            <!-- Techmeme Section -->
            <div id="techmeme-section" class="section-header" style="color: var(--techmeme-accent);">
                <i class="fas fa-bolt"></i>
                <h2>Techmeme Top 10</h2>
                <p class="section-desc"><i class="far fa-calendar-alt"></i> {datetime.now().strftime('%Y-%m-%d')}</p>
            </div>
            <div id="techmeme-grid" class="news-grid">'''
    
    for item in items:
        source_name = item.get('source', item.get('media_source', 'Source'))
        # Fallback if source is missing or empty
        if not source_name:
             source_name = "Read Story"

        html += f'''
                <div class="news-card" style="border-top: 6px solid var(--techmeme-accent);">
                    <div class="title-cn">{item.get('title_zh', '')}</div>
                    <div class="title-en">{item.get('title_en', '')}</div>
                    <a href="{item.get('url', '#')}" class="link-btn" style="color: var(--techmeme-accent);">{source_name} &rarr;</a>
                </div>'''
    html += '''
            </div>'''
    return html

def render_wsj(items):
    html = ""
    # Header
    html += f'''
            <!-- WSJ Section -->
            <div id="wsj-section" class="section-header" style="color: var(--wsj-accent);">
                <i class="fas fa-newspaper"></i>
                <h2>WSJ Technology Top 10</h2>
                <p class="section-desc"><i class="far fa-calendar-alt"></i> {datetime.now().strftime('%Y-%m-%d')}</p>
            </div>
            <div id="wsj-grid" class="news-grid">'''
    
    for item in items:
        html += f'''
                <div class="news-card" style="border-top: 6px solid var(--wsj-accent);">
                    <div class="title-cn">{item.get('title_zh', '')}</div>
                    <div class="title-en">{item.get('title_en', '')}</div>
                    <div class="summary-cn">{item.get('summary_zh', '')}</div>
                    <a href="{item.get('url', '#')}" class="link-btn" style="color: var(--wsj-accent);">WSJ &rarr;</a>
                </div>'''
    html += '''
            </div>'''
    return html

def render_deep_analysis(data):
    html = ""
    # Header
    html += '''
            <!-- Deep Analysis Section -->
            <div id="analysis-section" class="section-header" style="color: var(--analysis-accent);">
                <i class="fas fa-feather-alt"></i>
                <h2>Deep Analysis</h2>
                <p class="section-desc">Daily Intelligence</p>
            </div>
            <div id="deep-analysis-container">'''
    
    analysis_items = []
    
    if isinstance(data, dict):
         # If it has a 'title' key directly, treat it as a single item
         if 'title' in data:
             analysis_items.append(data)
         else:
            # If it's a dictionary of sources (e.g., Stratechery: {...})
            for source, content in data.items():
                if isinstance(content, dict):
                    analysis_items.append(content)
    elif isinstance(data, list):
        analysis_items = data

    for i, item in enumerate(analysis_items):
        # Generate a unique ID for the toggle
        toggle_id = f"analysis-toggle-{i}"
        
        # Determine title and summary keys (flexible fallback)
        title = item.get('title', item.get('title_zh', 'Deep Analysis'))
        summary = item.get('summary', item.get('content', item.get('summary_zh', '')))
        url = item.get('url', '#')
        
        # Handle Insights if present
        insights_html = ""
        if 'insights' in item and isinstance(item['insights'], list):
            insights_html = "<br><br><strong>關鍵洞察：</strong><br>"
            for idx, insight in enumerate(item['insights']):
                if isinstance(insight, dict):
                    topic = insight.get('topic', '')
                    text = insight.get('insight', '')
                    insights_html += f"{idx+1}. <strong>{topic}：</strong> {text}<br>"
                else:
                    # Fallback for simple string lists
                    insights_html += f"{idx+1}. {insight}<br>"

        full_content = summary + insights_html

        html += f'''
                <div class="news-card" style="border-top: 6px solid var(--analysis-accent); margin-bottom: 40px;">
                    <h3 style="font-size: 1.6rem; font-weight: bold; margin-top: 0;">{title}</h3>
                    <a href="{url}" style="color: var(--analysis-accent); font-weight: bold; text-decoration: none;">Original Source Link &rarr;</a>
                    <div class="expand-wrapper" id="{toggle_id}">
                        <div class="analysis-content" style="margin-top: 20px; line-height: 1.8;">
                            {full_content}
                        </div>
                        <div class="fade-mask"></div>
                    </div>
                    <button class="toggle-btn" onclick="toggleAnalysis('{toggle_id}')">展開全文 👀</button>
                </div>'''

    html += '''
            </div>'''
    return html

def main():
    print("Starting news render process...")
    data = load_data()
    
    # Handle case-insensitive keys (Techmeme vs techmeme)
    techmeme_data = data.get('Techmeme') or data.get('techmeme') or []
    wsj_data = data.get('WSJ_Technology') or data.get('wsj') or []
    deep_analysis_data = data.get('Deep_Analysis') or data.get('deep_analysis') or {}
    
    # Render sections
    techmeme_html = render_techmeme(techmeme_data)
    wsj_html = render_wsj(wsj_data) 
    deep_analysis_html = render_deep_analysis(deep_analysis_data)
    
    full_news_html = f"\n            <!-- DAILY_NEWS_START -->{techmeme_html}\n{wsj_html}\n{deep_analysis_html}\n            <!-- DAILY_NEWS_END -->"
    
    # Read index.html
    if not os.path.exists(HTML_PATH):
        print(f"Error: {HTML_PATH} not found.")
        sys.exit(1)
        
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Surgical replacement using Regex
    pattern = r'(<!-- DAILY_NEWS_START -->)([\s\S]*?)(<!-- DAILY_NEWS_END -->)'
    
    # Verify tags exist
    if not re.search(pattern, content):
        print("Error: DAILY_NEWS territory tags not found in index.html.")
        sys.exit(1)
        
    new_content = re.sub(pattern, full_news_html, content)
    
    # Write back
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
    print("Successfully updated index.html with latest news.")

if __name__ == "__main__":
    main()
