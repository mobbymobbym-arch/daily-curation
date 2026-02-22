import json
import os
import re

def render_to_html():
    json_path = "podcast_data.json"
    html_path = "index.html"
    
    # 1. 防呆檢查：確保 JSON 檔案存在
    if not os.path.exists(json_path):
        print("❌ 錯誤：找不到 podcast_data.json。請確認分析官已經寫入資料。")
        return
        
    # 2. 讀取完整的 JSON 資料 (包含章節)
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            title = data.get("title", "無標題")
            summary = data.get("summary", "無摘要內容")
            # 嘗試讀取章節陣列，如果沒有則給予空列表
            chapters = data.get("chapters", [])
    except Exception as e:
        print(f"❌ 錯誤：讀取 JSON 失敗 ({str(e)})")
        return
        
    # 3. 檢查 HTML 檔案是否存在
    if not os.path.exists(html_path):
        print(f"❌ 錯誤：找不到 {html_path}。")
        return
        
    # 4. 開始組裝帶有 Vibe 風格的 HTML 內容
    # 這裡包含了深紫色主題、字體設定，以及「展開全文」的互動邏輯
    html_builder = []
    
    # 主標題與大綱區塊
    html_builder.append('<div class="podcast-highlight-card" style="font-family: sans-serif; background-color: #f9f9f9; padding: 25px; border-radius: 12px; border-left: 6px solid #4a154b; margin-bottom: 20px;">')
    html_builder.append(f'  <h2 style="color: #4a154b; margin-top: 0;">{title}</h2>')
    html_builder.append(f'  <p style="font-size: 1.1em; line-height: 1.6; color: #333; font-weight: 500;">{summary}</p>')
    
    # 如果有章節內容，才加入展開按鈕與隱藏區塊
    if chapters:
        # 互動按鈕：透過簡單的 onclick 切換顯示狀態
        html_builder.append('  <button onclick="var content = document.getElementById(\'podcast-chapters-content\'); if(content.style.display === \'none\'){ content.style.display = \'block\'; this.innerText = \'收合全文 🔼\'; } else { content.style.display = \'none\'; this.innerText = \'展開全文 👀\'; }" style="background-color: #4a154b; color: white; border: none; padding: 10px 18px; border-radius: 6px; cursor: pointer; font-size: 1em; font-weight: bold; margin-top: 10px; transition: 0.3s;">展開全文 👀</button>')
        
        # 預設隱藏的章節內容區塊
        html_builder.append('  <div id="podcast-chapters-content" style="display: none; margin-top: 25px; border-top: 1px solid #ddd; padding-top: 20px;">')
        
        # 跑迴圈把每一個章節渲染出來
        for chapter in chapters:
            ch_time = chapter.get("timestamp", "")
            ch_title = chapter.get("title", "未命名章節") # 配合 podcast_data.json 欄位名為 title
            ch_content = chapter.get("content", "")
            ch_quote = chapter.get("quote", "")
            
            html_builder.append(f'    <div class="podcast-chapter" style="margin-bottom: 25px;">')
            # 時間軸與章節標題
            html_builder.append(f'      <h3 style="color: #2c3e50; font-size: 1.2em; margin-bottom: 10px;"><span style="color: #4a154b; background-color: #f0e6f2; padding: 2px 8px; border-radius: 4px; font-size: 0.9em; margin-right: 8px;">⏱️ {ch_time}</span>{ch_title}</h3>')
            # 深度敘事
            html_builder.append(f'      <p style="line-height: 1.7; color: #444;">{ch_content}</p>')
            # 名言引用 (如果有提供的話)
            if ch_quote:
                html_builder.append(f'      <blockquote style="background-color: #f3eaf5; border-left: 4px solid #8e44ad; padding: 12px 20px; margin: 15px 0; font-style: italic; color: #555;">「{ch_quote}」</blockquote>')
            html_builder.append('    </div>')
            
        html_builder.append('  </div>') # 關閉章節內容區塊
        
    html_builder.append('</div>') # 關閉整張卡片
    
    # 將陣列組合成一段完整的 HTML 字串
    new_podcast_html = "\n".join(html_builder)
    
    # 5. 讀取並更新 index.html
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
        
    # 定義安全防護區間的標記
    start_marker = "<!-- PODCAST_HIGHLIGHTS_START -->"
    end_marker = "<!-- PODCAST_HIGHLIGHTS_END -->"
    
    # 檢查網頁裡有沒有我們設定好的「安全區間」
    if start_marker not in html_content or end_marker not in html_content:
        print(f"❌ 錯誤：在 {html_path} 中找不到完整的區塊標記。")
        print(f"💡 請確保 index.html 中包含：\n{start_marker}\n（這裡放內容）\n{end_marker}")
        return

    # 使用 Regex 進行區段替換
    pattern = re.escape(start_marker) + r'[\s\S]*?' + re.escape(end_marker)
    replacement = f"{start_marker}\n{new_podcast_html}\n{end_marker}"
    updated_html = re.sub(pattern, replacement, html_content)
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(updated_html)
        
    print(f"✅ 成功！已將《{title}》的「極致 Vibe 渲染版」正式寫入 index.html。")

if __name__ == "__main__":
    render_to_html()
