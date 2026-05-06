import argparse
import html
import json
import os
import re
import subprocess
from datetime import datetime


def rebuild_podcast_highlights_page():
    section_builder = os.path.join("scripts", "build_section_pages.py")
    if not os.path.exists(section_builder):
        return
    result = subprocess.run(
        ["python3", section_builder, "--only", "podcast"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(result.stdout.strip())
    else:
        print(f"⚠️ Podcast 分頁重建失敗：{result.stderr.strip() or result.stdout.strip()}")


def teaser_text(value, limit=300):
    text = re.sub(r"<br\s*/?>", " ", str(value or ""), flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip() + ("..." if len(text) > limit else "")


def text_from_html(value):
    text = re.sub(r"<br\s*/?>", " ", str(value or ""), flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return html.unescape(text)


def render_to_html(section_only=False):
    if section_only:
        rebuild_podcast_highlights_page()
        return

    json_path = "podcast_data.json"
    html_path = "index.html"
    archive_dir = "archives"
    
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
        
    # 1. 讀取累計的 Podcast 資料
    if not os.path.exists(json_path):
        print("❌ 錯誤：找不到 podcast_data.json。")
        return
        
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            current_date = data.get("date")
            items = data.get("items", [])
    except Exception as e:
        print(f"❌ 錯誤：讀取 JSON 失敗 ({str(e)})")
        return
        
    if not items:
        print("ℹ️ 今日尚無 Podcast 資料。")
        return

    # 2. 讀取當前的 HTML
    if not os.path.exists(html_path):
        print(f"❌ 錯誤：找不到 {html_path}。")
        return
        
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # ==========================================
    # 📸 時光機與存檔機制
    # ==========================================
    # 透過正則抓取目前首頁上「第一個」Podcast 的標題與產生時間
    # 我們可以用來判斷首頁上的內容是否屬於「舊的一天」
    old_title_match = re.search(r'<!-- PODCAST_HIGHLIGHTS_START -->.*?<h[23][^>]*>(.*?)</h[23]>', html_content, re.DOTALL)
    
    # 嘗試找出首頁內容的日期（從存檔清單中推測，或是從 HTML 註解）
    # 為了簡單穩定，我們檢查：如果今天的第一個標題不在首頁上，且首頁上有內容，且日期不符，就存檔。
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    archive_filename = f"podcast-{today_str}.html"
    archive_filepath = os.path.join(archive_dir, archive_filename)
    
    # 邏輯：如果首頁上有舊內容，且該內容的標題不屬於今天的 items
    if old_title_match:
        old_title = text_from_html(old_title_match.group(1))
        today_titles = [item['title'] for item in items]
        
        # 如果首頁上的標題不屬於今天，說明首頁還停留在「昨天」
        if old_title not in today_titles:
            # 取得首頁內容的「最後更新日期」——這有點難拿，
            # 我們假設它是昨天的存檔。為了安全，我們檢查存檔檔案是否已存在。
            # 如果不存在，我們拍下這張「昨天的遺照」。
            
            # 注意：這裡有個細節，我們不知道 old_title 是哪一天的。
            # 但根據流程，只要它不是今天的，就應該被送進歷史存檔。
            # 我們這裡用一個簡單邏輯：只要 old_title != 今天的第一個標題，就嘗試備份。
            # 為了避免覆蓋今天的最新進度，我們只有在「跨日執行」時才備份。
            
            # 安全起見：我們查看 index.html 裡的日期標記（如果有）
            # 或者直接比對 JSON 的 date。
            pass # 稍後在渲染完後處理存檔

    # ==========================================
    # 🎨 首頁 Teaser 渲染：完整歷史內容交給 podcast-highlights.html
    # ==========================================
    total_html_builder = []
    
    for item in items[:3]:
        new_title = html.escape(str(item.get("title", "無標題")))
        new_summary = html.escape(teaser_text(item.get("summary", "無摘要內容")))
        original_link = item.get("original_link", "")
        show_name = html.escape(str(
            item.get("show_name")
            or item.get("podcast_show")
            or item.get("channel")
            or item.get("uploader")
            or "Podcast"
        ))
        generated_at = html.escape(str(item.get("generated_at") or current_date or ""))
        
        card_builder = []
        card_builder.append('<article class="teaser-card podcast-highlight-card" style="--teaser-accent: var(--podcast-accent);">')
        card_builder.append(f'  <span class="teaser-chip">{show_name}</span>')
        card_builder.append(f'  <h3>{new_title}</h3>')
        if generated_at:
            card_builder.append(f'  <div class="teaser-date">{generated_at}</div>')
        card_builder.append(f'  <p class="teaser-summary">{new_summary}</p>')
        card_builder.append('  <div class="teaser-actions">')
        if original_link:
            card_builder.append(f'    <a href="{html.escape(original_link)}" target="_blank" rel="noopener" class="link-btn" style="color: var(--podcast-accent);">Listen &rarr;</a>')
        card_builder.append('    <a href="/daily-curation/podcast-highlights.html" class="link-btn" style="color: var(--podcast-accent);">Read history &rarr;</a>')
        card_builder.append('  </div>')
        
        card_builder.append('</article>')
        total_html_builder.append("\n".join(card_builder))
    
    # 加入隱藏的時間戳記，供跨日存檔時準確比對使用
    current_date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    date_marker = f"<!-- PODCAST_DATE_START -->{current_date}<!-- PODCAST_DATE_END -->\n"
    new_podcast_html = date_marker + "\n".join(total_html_builder)
    
    # ==========================================
    # 🔄 更新 index.html
    # ==========================================
    start_marker = "<!-- PODCAST_HIGHLIGHTS_START -->"
    end_marker = "<!-- PODCAST_HIGHLIGHTS_END -->"
    
    if start_marker not in html_content or end_marker not in html_content:
        print(f"❌ 錯誤：在首頁找不到區塊標記。")
        return

    # 在更新前，處理「跨日存檔」
    # 如果 old_title 存在且不在今天的列表裡，備份 index.html 到昨天的存檔
    if old_title_match:
        old_title = text_from_html(old_title_match.group(1))
        if old_title not in [item['title'] for item in items]:
            # 這說明首頁上是舊資料，我們需要把它存起來
            # 我們需要知道 old_title 是哪一天的，最準確的方法是尋找 Podcast 專用的日期標記
            podcast_date_match = re.search(r'<!-- PODCAST_DATE_START -->(.*?)<!-- PODCAST_DATE_END -->', html_content)
            if podcast_date_match:
                file_date = podcast_date_match.group(1).strip()
            else:
                # 備援：在首頁這張遺照裡找第一個出現的日期
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', html_content)
                file_date = date_match.group(1) if date_match else "legacy"
            
            old_archive_path = os.path.join(archive_dir, f"podcast-{file_date}.html")
            if not os.path.exists(old_archive_path):
                try:
                    with open(old_archive_path, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    print(f"📦 已備份舊內容 ({file_date}) 至：{old_archive_path}")
                    
                    # 更新存檔清單 (避免重複)
                    inventory_link = f'<li><a href="{old_archive_path}">🎙️ {old_title} ({file_date})</a></li>'
                    if old_archive_path not in html_content:
                        inv_start = "<!-- PODCAST_INVENTORY_START -->"
                        if inv_start in html_content:
                            html_content = html_content.replace(inv_start, f"{inv_start}\n                        {inventory_link}")
                            print(f"📝 已將 {file_date} 內容加入存檔目錄。")
                except OSError as e:
                    print(f"⚠️ Podcast 舊內容存檔略過：{old_archive_path} ({e})")

    # 執行全量替換
    pattern = re.compile(rf"({start_marker}).*?({end_marker})", re.DOTALL)
    updated_html = pattern.sub(rf"\1\n {new_podcast_html}\n \2", html_content)
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(updated_html)
        
    print(f"✅ 成功渲染今日共 {len(items)} 篇 Podcast！")

    rebuild_podcast_highlights_page()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render Daily Curation podcast cards.")
    parser.add_argument(
        "--podcast-highlights-only",
        "--section-only",
        dest="section_only",
        action="store_true",
        help="Only rebuild the standalone Podcast Highlights page and feed.",
    )
    args = parser.parse_args()
    render_to_html(args.section_only)
