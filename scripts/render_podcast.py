import json
import os
import re
from datetime import datetime

def render_to_html():
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
    old_title_match = re.search(r'<!-- PODCAST_HIGHLIGHTS_START -->.*?<h2[^>]*>(.*?)</h2>', html_content, re.DOTALL)
    
    # 嘗試找出首頁內容的日期（從存檔清單中推測，或是從 HTML 註解）
    # 為了簡單穩定，我們檢查：如果今天的第一個標題不在首頁上，且首頁上有內容，且日期不符，就存檔。
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    archive_filename = f"podcast-{today_str}.html"
    archive_filepath = os.path.join(archive_dir, archive_filename)
    
    # 邏輯：如果首頁上有舊內容，且該內容的標題不屬於今天的 items
    if old_title_match:
        old_title = old_title_match.group(1).strip()
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
    # 🎨 全量渲染：組裝所有卡片
    # ==========================================
    total_html_builder = []
    
    for idx, item in enumerate(items):
        new_title = item.get("title", "無標題")
        new_summary = item.get("summary", "無摘要內容")
        chapters = item.get("chapters", [])
        original_link = item.get("original_link", "")
        
        card_builder = []
        card_builder.append('<div class="podcast-highlight-card" style="font-family: sans-serif; background-color: #f9f9f9; padding: 25px; border-radius: 12px; border-left: 6px solid #4a154b; margin-bottom: 20px;">')
        card_builder.append(f'  <h2 style="color: #4a154b; margin-top: 0;">{new_title}</h2>')
        card_builder.append(f'  <p style="font-size: 1.1em; line-height: 1.6; color: #333; font-weight: 500;">{new_summary}</p>')
        
        if chapters:
            # 使用索引確保 ID 唯一
            content_id = f"podcast-chapters-content-{idx}"
            card_builder.append(f'  <button onclick="var content = document.getElementById(\'{content_id}\'); if(content.style.display === \'none\'){{ content.style.display = \'block\'; this.innerText = \'收合全文 🔼\'; }} else {{ content.style.display = \'none\'; this.innerText = \'展開全文 👀\'; }}" style="background-color: #4a154b; color: white; border: none; padding: 10px 18px; border-radius: 6px; cursor: pointer; font-size: 1em; font-weight: bold; margin-top: 10px; transition: 0.3s;">展開全文 👀</button>')
            card_builder.append(f'  <div id="{content_id}" style="display: none; margin-top: 25px; border-top: 1px solid #ddd; padding-top: 20px;">')
            
            for chapter in chapters:
                ch_time = chapter.get("timestamp", "")
                ch_title = chapter.get("title") or chapter.get("chapter_title") or "未命名章節"
                ch_content = chapter.get("content", "")
                ch_quote = chapter.get("quote", "")
                
                card_builder.append(f'    <div class="podcast-chapter" style="margin-bottom: 25px;">')
                card_builder.append(f'      <h3 style="color: #2c3e50; font-size: 1.2em; margin-bottom: 10px;"><span style="color: #4a154b; background-color: #f0e6f2; padding: 2px 8px; border-radius: 4px; font-size: 0.9em; margin-right: 8px;">⏱️ {ch_time}</span>{ch_title}</h3>')
                card_builder.append(f'      <p style="line-height: 1.7; color: #444;">{ch_content}</p>')
                if ch_quote:
                    card_builder.append(f'      <blockquote style="background-color: #f3eaf5; border-left: 4px solid #8e44ad; padding: 12px 20px; margin: 15px 0; font-style: italic; color: #555;">「{ch_quote}」</blockquote>')
                card_builder.append('    </div>')
            card_builder.append('  </div>')
        
        if original_link:
            card_builder.append(f'  <a href="{original_link}" target="_blank" style="display: block; margin-top: 15px; color: #4a154b; font-weight: bold; text-decoration: none;">🎧 收聽原始節目 &rarr;</a>')
        
        card_builder.append('</div>')
        total_html_builder.append("\n".join(card_builder))
    
    new_podcast_html = "\n".join(total_html_builder)
    
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
        old_title = old_title_match.group(1).strip()
        if old_title not in [item['title'] for item in items]:
            # 這說明首頁上是舊資料，我們需要把它存起來
            # 我們需要知道 old_title 是哪一天的，但既然它不是今天的，我們就用「現在首頁」日期（通常是昨天）
            # 這裡我們簡化：在首頁找第一個出現的日期
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', html_content)
            file_date = date_match.group(1) if date_match else "legacy"
            
            old_archive_path = os.path.join(archive_dir, f"podcast-{file_date}.html")
            if not os.path.exists(old_archive_path):
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

    # 執行全量替換
    pattern = re.compile(rf"({start_marker}).*?({end_marker})", re.DOTALL)
    updated_html = pattern.sub(rf"\1\n {new_podcast_html}\n \2", html_content)
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(updated_html)
        
    print(f"✅ 成功渲染今日共 {len(items)} 篇 Podcast！")

if __name__ == "__main__":
    render_to_html()
