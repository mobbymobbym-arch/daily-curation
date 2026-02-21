import json
import re
import sys
import os

# 設定檔案路徑
JSON_PATH = 'podcast_data.json'
HTML_PATH = 'index.html'

def main():
    # 1. 讀取 Podcast 數據
    if not os.path.exists(JSON_PATH):
        print(f"⚠️ 找不到 {JSON_PATH}，請確認分析官已完成摘要寫作。")
        sys.exit(1)
        
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 2. 生成 Podcast HTML 結構 (繼承 🌵 敘事風格)
    chapters_html = ""
    for chapter in data.get('chapters', []):
        chapters_html += f"""
                        <div style="margin-top: 20px;">
                            <h3 style="color: var(--podcast-accent); border-bottom: 1px solid #eee; padding-bottom: 5px;">{chapter.get('title')} ({chapter.get('timestamp')})</h3>
                            <p style="line-height: 1.8; color: #333;">{chapter.get('content')}</p>
                            <blockquote style="font-style: italic; color: #666; border-left: 4px solid #ddd; padding-left: 10px; margin: 10px 0;">
                                "{chapter.get('quote')}"
                            </blockquote>
                        </div>
        """

    podcast_html = f"""
                <div class="news-card" style="border-top: 6px solid var(--podcast-accent); margin-bottom: 30px;">
                    <div class="title-cn">🎙️ {data.get('title', '今日深度 Podcast 摘要')}</div>
                    <div class="title-en" style="margin-bottom: 10px;">🗓️ 更新日期：2026-02-21 | 素材來源：{data.get('source_type')}</div>
                    <div class="expand-wrapper" id="pod-wrap-latest">
                        <div class="summary-cn" style="border-left-color: var(--podcast-accent); padding-left: 15px; margin-bottom: 0;">
                            <p><strong>核心主題：</strong>{data.get('summary')}</p>
                            {chapters_html}
                            <hr style="margin-top: 20px; border: 0; border-top: 1px dashed #ccc;">
                            <p style="font-size: 0.9em; color: #666;">
                                <strong>主持人/來賓：</strong>{data.get('host')} / {data.get('guest')}<br>
                                <strong>原始連結：</strong><a href="{data.get('source_url')}" target="_blank">{data.get('source_url')}</a>
                            </p>
                        </div>
                        <div class="fade-mask"></div>
                    </div>
                    <div style="margin-top: 15px; display: flex; gap: 15px; align-items: center;">
                        <button class="toggle-btn" onclick="const wrapper = this.parentElement.previousElementSibling; wrapper.classList.toggle('expanded'); this.innerText = wrapper.classList.contains('expanded') ? '收起內容' : '展開全文 👀'">展開全文 👀</button>
                        <a href="{data.get('source_url')}" target="_blank" style="color: var(--podcast-accent); text-decoration: none; font-weight: bold;"> 🎧 收聽來源 </a>
                    </div>
                </div>
"""

    # 3. 讀取目前的 index.html
    if not os.path.exists(HTML_PATH):
        print(f"❌ 錯誤：找不到 {HTML_PATH}")
        sys.exit(1)

    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # 4. 外科手術式替換 (Regex)
    pattern = r'(<!-- PODCAST_HIGHLIGHTS_START -->)([\s\S]*?)(<!-- PODCAST_HIGHLIGHTS_END -->)'
    
    if not re.search(pattern, content):
        print("❌ 錯誤：在 index.html 中找不到 Podcast 領土標籤 (PODCAST_HIGHLIGHTS_START)！")
        sys.exit(1)

    # 將生成的 HTML 塞入標籤中間
    new_content = re.sub(pattern, rf'\g<1>{podcast_html}\g<3>', content)

    # 5. 存檔寫回
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print("✅ Podcast 區塊局部更新成功！")

if __name__ == "__main__":
    main()
