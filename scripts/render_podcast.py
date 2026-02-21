import json
import re
import sys
import os

# 設定檔案路徑
JSON_PATH = 'podcast_data.json'
HTML_PATH = 'index.html'

def main():
    # 1. 讀取 Podcast 數據 (由分析官 Gemini 產生)
    if not os.path.exists(JSON_PATH):
        print(f"⚠️ 找不到 {JSON_PATH}，請確認分析官已完成摘要寫作。")
        sys.exit(1)
        
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # 如果 JSON 是一個列表，取最後一筆 (最新)
        if isinstance(data, list):
            data = data[-1]

    # 2. 生成 Podcast HTML 結構 (繼承 🌵 敘事風格)
    # 注意：這裡的 HTML 標籤會完美成對，不會弄壞網頁
    podcast_html = f"""
                <div class="news-card" style="border-top: 6px solid var(--podcast-accent); margin-bottom: 30px;">
                    <div class="title-cn">🎙️ {data.get('title', '今日深度 Podcast 摘要')}</div>
                    <div class="title-en" style="margin-bottom: 10px;">🗓️ 更新日期：{data.get('date', '2026-02-21')}</div>
                    <div class="expand-wrapper" id="pod-wrap-latest">
                        <div class="summary-cn" style="border-left-color: var(--podcast-accent); padding-left: 15px; margin-bottom: 0;">
                            {data.get('summary_narrative', '<p>摘要生成中...</p>')}
                        </div>
                        <div class="fade-mask"></div>
                    </div>
                    <div style="margin-top: 15px; display: flex; gap: 15px; align-items: center;">
                        <button class="toggle-btn" onclick="const wrapper = this.parentElement.previousElementSibling; wrapper.classList.toggle('expanded'); this.innerText = wrapper.classList.contains('expanded') ? '收起內容' : '展開全文 👀'">展開全文 👀</button>
                        <a href=\"{data.get('original_link', '#')}\" target=\"_blank\" style=\"color: var(--podcast-accent); text-decoration: none; font-weight: bold;\"> 🎧 收聽來源 </a>
                    </div>
                </div>
"""

    # 3. 讀取目前的 index.html
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # 4. 外科手術式替換 (Regex) - 絕對不碰 Daily News 區塊
    # 使用主人提供的標準標籤
    pattern = r'(<!-- PODCAST_HIGHLIGHTS_START -->)([\s\S]*?)(<!-- PODCAST_HIGHLIGHTS_END -->)'
    
    if not re.search(pattern, content):
        print("❌ 錯誤：在 index.html 中找不到 Podcast 領土標籤 (PODCAST_HIGHLIGHTS_START)！")
        sys.exit(1)

    # 將生成的 HTML 塞入標籤中間
    new_content = re.sub(pattern, rf'\g<1>{podcast_html}\g<3>', content)

    # 5. 存檔寫回
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print("✅ Podcast 區塊局部更新成功！新聞區塊安全無虞。")

if __name__ == "__main__":
    main()
