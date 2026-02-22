import json
import os

def render_to_html():
    json_path = "podcast_data.json"
    html_path = "index.html"
    
    # 1. 檢查 JSON 檔案是否存在
    if not os.path.exists(json_path):
        print("❌ 錯誤：找不到 podcast_data.json。請確認分析官已經寫入資料。")
        return
        
    # 2. 生成 Podcast HTML 結構 (包含完整章節與極致敘事風格)
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            title = data.get("title", "無標題")
            summary = data.get("summary", "無摘要內容")
            chapters = data.get("chapters", [])
            date = data.get("date", "2026-02-22")
            source_type = data.get("source_type", "素材分析")
            source_url = data.get("source_url", "#")
            host = data.get("host", "未知主持人")
            guest = data.get("guest", "未知來賓")

        # 組合章節內容
        chapters_html = ""
        for chapter in chapters:
            chapters_html += f"""
                        <div style="margin-top: 25px;">
                            <h3 style="color: var(--podcast-accent); border-bottom: 1px solid rgba(139, 92, 246, 0.1); padding-bottom: 8px; font-size: 1.2rem;">{chapter.get('title')} ({chapter.get('timestamp')})</h3>
                            <p style="line-height: 1.8; color: #374151; font-size: 1.05rem;">{chapter.get('content')}</p>
                            <blockquote style="font-style: italic; color: #6b7280; border-left: 4px solid var(--podcast-accent); padding-left: 15px; margin: 20px 0; background: rgba(139, 92, 246, 0.03); padding: 15px;">
                                "{chapter.get('quote')}"
                            </blockquote>
                        </div>
            """

        new_html_block = f"""{insertion_marker}
                <div class="news-card" style="border-top: 6px solid var(--podcast-accent); margin-bottom: 30px;">
                    <div class="title-cn">🎙️ {title}</div>
                    <div class="title-en" style="margin-bottom: 10px;">🗓️ 更新日期：{date} | 素材來源：{source_type}</div>
                    
                    <div class="expand-wrapper" id="pod-wrap-latest">
                        <div class="summary-cn" style="border-left-color: var(--podcast-accent); padding-left: 15px; margin-bottom: 0;">
                            <p style="font-weight: 800; font-size: 1.1rem; color: var(--primary-text);">【核心主題】</p>
                            <p>{summary}</p>
                            
                            {chapters_html}
                            
                            <hr style="margin-top: 30px; border: 0; border-top: 1px dashed #ccc;">
                            <p style="font-size: 0.9em; color: #666;">
                                <strong>主持人/來賓：</strong>{host} / {guest}<br>
                                <strong>原始連結：</strong><a href="{source_url}" target="_blank">{source_url}</a>
                            </p>
                        </div>
                        <div class="fade-mask"></div>
                    </div>
                    
                    <div style="margin-top: 15px; display: flex; gap: 15px; align-items: center;">
                        <button class="toggle-btn" onclick="const wrapper = this.parentElement.previousElementSibling; wrapper.classList.toggle('expanded'); this.innerText = wrapper.classList.contains('expanded') ? '收起內容' : '展開全文 👀'">展開全文 👀</button>
                        <a href="{source_url}" target="_blank" style="color: var(--podcast-accent); text-decoration: none; font-weight: bold; font-size: 0.9rem;"> 🎧 收聽來源 </a>
                    </div>
                </div>
"""
    except Exception as e:
        print(f"❌ 錯誤：生成 HTML 失敗 ({str(e)})")
        return
    
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
