import json
import re
import os

# 設定檔案路徑
JSON_FILE = 'podcast_data.json'
INDEX_FILE = 'index.html'

def sync_all():
    # 0. 檢查 JSON 檔案是否存在
    if not os.path.exists(JSON_FILE):
        print(f"⚠️ 找不到 {JSON_FILE}，請確認檔案位置。")
        return

    # 1. 讀取所有 Podcast 資料
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
    except json.JSONDecodeError:
        print(f"⚠️ {JSON_FILE} 格式錯誤，無法讀取。")
        return

    # 確保資料按日期排序 (最新的在前)
    data_list.sort(key=lambda x: x['date'], reverse=True)

    # 2. 生成首頁最新的 3 張卡片 HTML
    highlights_html = ""
    for i, data in enumerate(data_list[:3]): # 只取前三則
        highlights_html += f'''
                <div class="news-card" style="border-top: 6px solid var(--podcast-accent); margin-bottom: 30px;">
                    <div class="title-cn">🎙️ {data['title']}</div>
                    <div class="title-en" style="margin-bottom: 10px;">🗓️ 更新日期：{data['date']}</div>
                    <div class="expand-wrapper" id="pod-wrap-{i}">
                        <div class="summary-cn" style="border-left-color: var(--podcast-accent); padding-left: 15px; margin-bottom: 0;">
                            {data['summary']}
                        </div>
                        <div class="fade-mask"></div>
                    </div>
                    <div style="margin-top: 15px; display: flex; gap: 15px; align-items: center;">
                        <button class="toggle-btn" onclick="const wrapper = this.parentElement.previousElementSibling; wrapper.classList.toggle('expanded'); this.innerText = wrapper.classList.contains('expanded') ? '收起內容' : '展開全文 👀'">展開全文 👀</button>
                        <a href="{data['url']}" target="_blank" style="color: var(--podcast-accent); text-decoration: none; font-weight: bold;"> 🎧 收聽來源 </a>
                    </div>
                </div>'''

    # 3. 生成側邊欄完整的存檔清單 HTML
    archive_html = "\n                        "
    for data in data_list:
        archive_html += f'<li><a href="{data["url"]}" target="_blank">🎙️ {data["title"]}</a></li>\n                        '
    archive_html += ""

    # 4. 寫入 index.html
    try:
        with open(INDEX_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"⚠️ 找不到 {INDEX_FILE}，請確認檔案位置。")
        return

    # 精準替換首頁容器內容
    content = re.sub(r'(<div id="podcast-highlights-container">)(.*?)(</div>)', rf'\1 {highlights_html} \3', content, flags=re.DOTALL)
    
    # 精準替換存檔清單內容
    content = re.sub(r'(<ul id="podcast-archive-list"[^>]*>)(.*?)(</ul>)', rf'\1 {archive_html} \3', content, flags=re.DOTALL)

    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ 同步成功！首頁已更新最新 3 則，存檔目錄已同步共 {len(data_list)} 則。")

if __name__ == "__main__":
    sync_all()
