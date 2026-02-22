import json
import os
import re
from datetime import datetime

def render_to_html():
    json_path = "podcast_data.json"
    html_path = "index.html"
    archive_dir = "archives" # 我們建立一個專屬的檔案館資料夾
    
    # 確保檔案館資料夾存在，沒有的話自動建立
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
        
    # 1. 讀取分析官寫好的「新」Podcast 資料
    if not os.path.exists(json_path):
        print("❌ 錯誤：找不到 podcast_data.json。")
        return
        
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            new_title = data.get("title", "無標題")
            new_summary = data.get("summary", "無摘要內容")
            chapters = data.get("chapters", [])
    except Exception as e:
        print(f"❌ 錯誤：讀取 JSON 失敗 ({str(e)})")
        return
        
    # 2. 讀取「當前」的 HTML 網站內容
    if not os.path.exists(html_path):
        print(f"❌ 錯誤：找不到 {html_path}。")
        return
        
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # ==========================================
    # 📸 時光機機制：處理歷史存檔與目錄區更新
    # ==========================================
    # 透過正規表達式，抓取目前首頁上「舊的」Podcast 標題
    old_title_match = re.search(r'<!-- PODCAST_HIGHLIGHTS_START -->.*?<h2[^>]*>(.*?)</h2>', html_content, re.DOTALL)
    
    if old_title_match:
        old_title = old_title_match.group(1).strip()
        
        # 防呆機制：如果新舊標題一樣，代表可能只是重複執行腳本，就不做存檔以免產生垃圾檔案
        if old_title != new_title:
            today_str = datetime.now().strftime("%Y-%m-%d")
            archive_filename = f"podcast-{today_str}.html"
            archive_filepath = os.path.join(archive_dir, archive_filename)
            
            # 【動作 A】拍快照：把現在的 index.html 完整複製並存入 archives 資料夾
            with open(archive_filepath, 'w', encoding='utf-8') as archive_file:
                archive_file.write(html_content)
            print(f"📦 已將舊首頁《{old_title}》快照備份至：{archive_filepath}")
            
            # 【動作 B】建索引：準備要插入到右側目錄區的新連結
            archive_link_html = f'<li><a href="{archive_filepath}">🎙️ {old_title} ({today_str})</a></li>'
            
            # 尋找目錄區的「插座」並將新連結放在最上面
            archive_start = "<!-- PODCAST_INVENTORY_START -->"
            if archive_start in html_content:
                html_content = html_content.replace(
                    archive_start, 
                    f"{archive_start}\n                        {archive_link_html}"
                )
                print(f"📝 已將《{old_title}》加入 PODCAST 存檔目錄區！")

    # ==========================================
    # 🎨 渲染新內容：組裝新的 Podcast 主區塊
    # ==========================================
    html_builder = []
    html_builder.append('<div class="podcast-highlight-card" style="font-family: sans-serif; background-color: #f9f9f9; padding: 25px; border-radius: 12px; border-left: 6px solid #4a154b; margin-bottom: 20px;">')
    html_builder.append(f'  <h2 style="color: #4a154b; margin-top: 0;">{new_title}</h2>')
    html_builder.append(f'  <p style="font-size: 1.1em; line-height: 1.6; color: #333; font-weight: 500;">{new_summary}</p>')
    
    # 之前設計好的章節與展開按鈕邏輯 (完整保留)
    if chapters:
        html_builder.append('  <button onclick="var content = document.getElementById(\'podcast-chapters-content\'); if(content.style.display === \'none\'){ content.style.display = \'block\'; this.innerText = \'收合全文 🔼\'; } else { content.style.display = \'none\'; this.innerText = \'展開全文 👀\'; }" style="background-color: #4a154b; color: white; border: none; padding: 10px 18px; border-radius: 6px; cursor: pointer; font-size: 1em; font-weight: bold; margin-top: 10px; transition: 0.3s;">展開全文 👀</button>')
        html_builder.append('  <div id="podcast-chapters-content" style="display: none; margin-top: 25px; border-top: 1px solid #ddd; padding-top: 20px;">')
        
        for chapter in chapters:
            ch_time = chapter.get("timestamp", "")
            # 兼容處理：同時支持 title 和 chapter_title 欄位
            ch_title = chapter.get("title") or chapter.get("chapter_title") or "未命名章節"
            ch_content = chapter.get("content", "")
            ch_quote = chapter.get("quote", "")
            
            html_builder.append(f'    <div class="podcast-chapter" style="margin-bottom: 25px;">')
            html_builder.append(f'      <h3 style="color: #2c3e50; font-size: 1.2em; margin-bottom: 10px;"><span style="color: #4a154b; background-color: #f0e6f2; padding: 2px 8px; border-radius: 4px; font-size: 0.9em; margin-right: 8px;">⏱️ {ch_time}</span>{ch_title}</h3>')
            html_builder.append(f'      <p style="line-height: 1.7; color: #444;">{ch_content}</p>')
            if ch_quote:
                html_builder.append(f'      <blockquote style="background-color: #f3eaf5; border-left: 4px solid #8e44ad; padding: 12px 20px; margin: 15px 0; font-style: italic; color: #555;">「{ch_quote}」</blockquote>')
            html_builder.append('    </div>')
        html_builder.append('  </div>')
    html_builder.append('</div>')
    
    new_podcast_html = "\n".join(html_builder)
    
    # ==========================================
    # 🔄 覆蓋主畫面：將新內容寫入 index.html
    # ==========================================
    start_marker = "<!-- PODCAST_HIGHLIGHTS_START -->"
    end_marker = "<!-- PODCAST_HIGHLIGHTS_END -->"
    
    if start_marker not in html_content or end_marker not in html_content:
        print(f"❌ 錯誤：在 {html_path} 中找不到 {start_marker} 區塊標記。")
        return

    # 使用正規表達式 (Regex) 把 START 和 END 中間的所有東西，替換成我們剛剛做好的新 HTML
    # re.DOTALL 確保它可以跨越多行進行替換
    pattern = re.compile(rf"({start_marker}).*?({end_marker})", re.DOTALL)
    
    # \1 代表保留 start_marker，\2 代表保留 end_marker，中間塞入新的 HTML
    updated_html = pattern.sub(rf"\1\n {new_podcast_html}\n \2", html_content)
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(updated_html)
        
    print(f"✅ 真實渲染與歷史存檔大成功！已將《{new_title}》寫入主畫面。")

if __name__ == "__main__":
    render_to_html()
