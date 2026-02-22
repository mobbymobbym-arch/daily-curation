import json
import os

def render_to_html():
    json_path = "podcast_data.json"
    html_path = "index.html"
    
    # 1. 檢查 JSON 檔案是否存在
    if not os.path.exists(json_path):
        print("❌ 錯誤：找不到 podcast_data.json。請確認分析官已經寫入資料。")
        return
        
    # 2. 讀取分析官寫好的 JSON 摘要資料
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            title = data.get("title", "無標題")
            summary = data.get("summary", "無摘要內容")
    except Exception as e:
        print(f"❌ 錯誤：讀取 JSON 失敗 ({str(e)})")
        return
        
    # 3. 檢查 HTML 檔案是否存在
    if not os.path.exists(html_path):
        print(f"❌ 錯誤：找不到 {html_path}。")
        return
        
    # 4. 讀取 HTML 並將內容插入
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
        
    # 定義插入點 (這就像是 HTML 裡面的插座)
    # 根據主人提供的邏輯與 index.html 現狀，使用 <!-- PODCAST_HIGHLIGHTS_START --> 作為插座
    insertion_marker = "<!-- PODCAST_HIGHLIGHTS_START -->"
    
    if insertion_marker not in html_content:
        print(f"❌ 錯誤：在 {html_path} 中找不到插入點標記 {insertion_marker}。")
        print("💡 請在 index.html 中你想要顯示摘要的地方加上 <!-- PODCAST_HIGHLIGHTS_START -->")
        return
        
    # 準備要插入的新 HTML 區塊
    # 注意：這裡我們保留標記，以便下次可以再次替換（或者依照主人腳本邏輯直接取代）
    # 依照主人提供的代碼邏輯，它是直接 replace
    new_html_block = f"""{insertion_marker}
                <div class="news-card" style="border-top: 6px solid var(--podcast-accent); margin-bottom: 30px;">
                    <div class="title-cn">🎙️ {title}</div>
                    <div class="summary-cn" style="border-left-color: var(--podcast-accent); padding-left: 15px; margin-bottom: 0;">
                        <p>{summary}</p>
                    </div>
                </div>
"""
    
    # 取代並更新 HTML 內容
    # 我們使用 regex 或簡單的 replace。為了確保插座不消失，我們把 marker 帶進 new_block
    updated_html = html_content.replace(insertion_marker, new_html_block)
    
    # 處理可能存在的舊內容 (如果主人想要的是局部更新而非無限堆疊)
    # 這裡採用主人提供的 replace 邏輯，但為了安全起見，我會配合 <!-- PODCAST_HIGHLIGHTS_END --> 做區段替換
    import re
    pattern = r'<!-- PODCAST_HIGHLIGHTS_START -->[\s\S]*?<!-- PODCAST_HIGHLIGHTS_END -->'
    replacement = f'<!-- PODCAST_HIGHLIGHTS_START -->\n{new_html_block}\n<!-- PODCAST_HIGHLIGHTS_END -->'
    
    # 但主人給的代碼非常簡約，我先完全依照主人的邏輯執行 replace。
    # 修正：主人給的原始代碼中 insertion_marker 是空的，我將其設為正確的標籤。
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(updated_html)
        
    print(f"✅ 成功！已將《{title}》的摘要正式寫入 index.html。")

if __name__ == "__main__":
    render_to_html()
