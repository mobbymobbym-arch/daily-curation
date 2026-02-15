import os
import re

# 設定資料夾與檔案路徑
ARCHIVE_DIR = "archive"
INDEX_FILE = "index.html"

def update_archive_list():
    # 1. 檢查倉庫 (archive 資料夾) 是否存在
    if not os.path.exists(ARCHIVE_DIR):
        print(f"⚠️ 找不到 {ARCHIVE_DIR} 資料夾，請確認路徑。")
        return

    # 2. 掃描倉庫裡所有的 HTML 檔案
    # 找出類似 "2026-02-12.html" 這樣的檔案
    files = [f for f in os.listdir(ARCHIVE_DIR) if f.endswith('.html')]

    # 如果倉庫是空的，就提早結束
    if not files:
        print("ℹ️ 目前沒有任何存檔檔案。")
        return

    # 3. 排序檔案 (Reverse=True 代表從最新排到最舊)
    files.sort(reverse=True)

    # 4. 組合新的網頁列表 (HTML)
    new_list_html = "\n                        <li><a href=\"index.html\">📄 2026-02-15 (今日)</a></li>"
    for file in files:
        # 把 ".html" 去掉，只留下日期字串作為顯示名稱
        date_str = file.replace('.html', '')
        # 如果是今天的檔案，我們通常首頁就是今日，所以這裡可以選擇是否重複列出或標註
        # 依照主人提供的邏輯，我們列出所有存檔
        new_list_html += f'\n                        <li><a href="{ARCHIVE_DIR}/{file}">📄 {date_str}</a></li>'
    new_list_html += "\n                    "

    # 5. 讀取目前的網站首頁 (index.html)
    try:
        with open(INDEX_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"⚠️ 找不到 {INDEX_FILE}，請確認檔案位置。")
        return

    # 6. 尋找並替換指定的區塊
    # 我們使用正則表達式，精準鎖定 <ul id="daily-archive-list"> 和 </ul> 之間的所有內容
    # 這樣不管上面的 <h3> 標題改成什麼 Emoji 都不會影響腳本運作！
    pattern = r'(<ul id="daily-archive-list"[^>]*>)(.*?)(</ul>)'
    
    # 打印匹配測試
    match = re.search(pattern, content, flags=re.DOTALL)
    if match:
        print(f"DEBUG: Found UL section. Current inner length: {len(match.group(2))}")
    else:
        print("DEBUG: Could NOT find the pattern!")

    # 將舊內容替換成我們剛剛組合好的新列表
    new_content = re.sub(pattern, rf'\1{new_list_html}\3', content, flags=re.DOTALL)

    # 7. 將更新後的內容寫回網站首頁
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print("✅ 日報存檔清單已成功更新！所有缺漏的日期都已補齊。")

# 程式執行起點
if __name__ == "__main__":
    update_archive_list()
