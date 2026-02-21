import os
import re
import sys

ARCHIVE_DIR = 'archive'
INDEX_FILE = 'index.html'

def get_title_from_file(filepath):
    # 嘗試打開檔案，抓取 PODCAST_HIGHLIGHTS 區塊內的 title-cn 作為標題
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            # 優先尋找 Podcast 領土內的標題
            podcast_match = re.search(r'<!-- PODCAST_HIGHLIGHTS_START -->.*?<div class="title-cn">🎙️ (.*?)</div>', content, re.DOTALL)
            if podcast_match:
                return podcast_match.group(1).strip()
            
            # 備援：原本的 <h3> 邏輯，但排除掉通用標題
            h3_matches = re.findall(r'<h3[^>]*>(.*?)</h3>', content)
            for title in h3_matches:
                if "存檔" not in title and "日報" not in title:
                    return title.strip()
    except Exception:
        pass
    return "Podcast 深度摘要"

def main():
    if not os.path.exists(ARCHIVE_DIR):
        print(f"⚠️ 找不到 {ARCHIVE_DIR} 資料夾。")
        sys.exit(1)

    files = [f for f in os.listdir(ARCHIVE_DIR) if f.endswith('.html')]
    files.sort(reverse=True)  # 從最新排到最舊

    daily_links = []
    podcast_links = []

    for filename in files:
        filepath = os.path.join(ARCHIVE_DIR, filename)
        
        # 分類 A：純日報 (嚴格比對 YYYY-MM-DD.html)
        if re.match(r'^\d{4}-\d{2}-\d{2}\.html$', filename):
            date_str = filename.replace('.html', '')
            daily_links.append(f'<li><a href="archive/{filename}">📄 {date_str}</a></li>')
        
        # 分類 B：Podcast 專題 (檔名帶有 -podcast 或其他後綴)
        elif re.match(r'^\d{4}-\d{2}-\d{2}-.*\.html$', filename):
            date_match = re.search(r'^(\d{4}-\d{2}-\d{2})', filename)
            date_str = date_match.group(1) if date_match else "未知日期"
            title = get_title_from_file(filepath)
            podcast_links.append(f'<li><a href="archive/{filename}">🎙️ {title} ({date_str})</a></li>')

    # 組合 HTML
    daily_html = "\n                " + "\n                ".join(daily_links) if daily_links else "<li>尚無日報存檔</li>"
    podcast_html = "\n                " + "\n                ".join(podcast_links) if podcast_links else "<li>尚無 Podcast 存檔</li>"

    if not os.path.exists(INDEX_FILE):
        print(f"⚠️ 找不到 {INDEX_FILE}。")
        sys.exit(1)

    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # 替換左側日報區塊
    daily_pattern = r'(<!-- DAILY_INVENTORY_START -->)([\s\S]*?)(<!-- DAILY_INVENTORY_END -->)'
    if re.search(daily_pattern, content):
        content = re.sub(daily_pattern, rf'\g<1>{daily_html}\n                \g<3>', content)

    # 替換右側 Podcast 區塊
    podcast_pattern = r'(<!-- PODCAST_INVENTORY_START -->)([\s\S]*?)(<!-- PODCAST_INVENTORY_END -->)'
    if re.search(podcast_pattern, content):
        content = re.sub(podcast_pattern, rf'\g<1>{podcast_html}\n                \g<3>', content)

    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ 雙軌目錄更新完成！")

if __name__ == "__main__":
    main()
