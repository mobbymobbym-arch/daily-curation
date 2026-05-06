import os
import re
import sys

ARCHIVE_DIR = 'archives'
INDEX_FILE = 'index.html'

def main():
    if not os.path.exists(ARCHIVE_DIR):
        print(f"⚠️ 找不到 {ARCHIVE_DIR} 資料夾。")
        sys.exit(1)

    files = [f for f in os.listdir(ARCHIVE_DIR) if f.endswith('.html')]
    files.sort(reverse=True)  # 從最新排到最舊

    daily_links = []

    for filename in files:
        # 純日報 (嚴格比對 YYYY-MM-DD.html)
        if re.match(r'^\d{4}-\d{2}-\d{2}\.html$', filename):
            date_str = filename.replace('.html', '')
            import datetime
            today_str = datetime.datetime.now().strftime('%Y-%m-%d')
            
            if date_str == today_str:
                daily_links.append(f'<li><a href="index.html">📄 {date_str} (今日)</a></li>')
            else:
                daily_links.append(f'<li><a href="archives/{filename}">📄 {date_str}</a></li>')

    # 組合 HTML
    daily_html = "\n                " + "\n                ".join(daily_links) if daily_links else "<li>尚無日報存檔</li>"

    if not os.path.exists(INDEX_FILE):
        print(f"⚠️ 找不到 {INDEX_FILE}。")
        sys.exit(1)

    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # 替換左側日報區塊
    daily_pattern = r'(<!-- DAILY_INVENTORY_START -->)([\s\S]*?)(<!-- DAILY_INVENTORY_END -->)'
    if re.search(daily_pattern, content):
        content = re.sub(daily_pattern, rf'\g<1>{daily_html}\n                \g<3>', content)

    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ 日報存檔目錄更新完成！")

if __name__ == "__main__":
    main()
