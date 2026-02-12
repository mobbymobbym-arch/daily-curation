import os
import re
from datetime import datetime

# 設定路徑
WORKSPACE = "/Users/lanreset/.openclaw/workspace"
ARCHIVE_DIR = os.path.join(WORKSPACE, "archive")
INDEX_PATH = os.path.join(WORKSPACE, "index.html")

def update_archives():
    # 1. 從 index.html 提取日期 (格式假設為 <p>Thursday, February 12, 2026</p>)
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 找尋日期文字
    date_match = re.search(r'<header>.*?<p>(.*?)</p>', content, re.DOTALL)
    if not date_match:
        print("找不到日期標籤")
        return

    date_str = date_match.group(1).strip()
    # 轉換成 YYYY-MM-DD 格式
    try:
        date_obj = datetime.strptime(date_str, "%A, %B %d, %Y")
        iso_date = date_obj.strftime("%Y-%m-%d")
    except ValueError:
        iso_date = datetime.now().strftime("%Y-%m-%d")

    # 2. 將當前 index.html 存檔到 archive 資料夾
    archive_filename = f"{iso_date}.html"
    archive_path = os.path.join(ARCHIVE_DIR, archive_filename)
    
    # 為了讓存檔能正確顯示，我們需要調整存檔內的連結 (例如回首頁)
    # 暫時直接複製，後續可優化
    with open(archive_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"已存檔: {archive_filename}")

    # 3. 掃描所有存檔並生成側邊欄 HTML
    archives = [f for f in os.listdir(ARCHIVE_DIR) if f.endswith('.html')]
    archives.sort(reverse=True) # 新的在前

    sidebar_html = '<ul class="archive-list">\n'
    # 加入今日連結 (index.html)
    sidebar_html += f'''                <li class="archive-item">
                    <a href="index.html" class="archive-link active">
                        <i class="far fa-calendar-check"></i> {iso_date} (今日)
                    </a>
                </li>\n'''
    
    # 加入歷史連結
    for arc in archives:
        date_label = arc.replace('.html', '')
        if date_label == iso_date: continue # 跳過今日，因為已經加過了
        
        sidebar_html += f'''                <li class="archive-item">
                    <a href="archive/{arc}" class="archive-link">
                        <i class="far fa-calendar"></i> {date_label}
                    </a>
                </li>\n'''
    sidebar_html += '            </ul>'

    # 4. 將新的側邊欄 HTML 寫回 index.html
    new_content = re.sub(
        r'<ul class="archive-list">.*?</ul>',
        sidebar_html,
        content,
        flags=re.DOTALL
    )

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("index.html 側邊欄已更新")

if __name__ == "__main__":
    update_archives()
