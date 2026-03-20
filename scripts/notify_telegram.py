import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime

import ssl

ssl._create_default_https_context = ssl._create_unverified_context

DAILY_NEWS_JSON = 'daily_news_temp.json'
TOKEN = "8293965702:AAH0ZxRwSSI8vhaiwbJb-A081v4u7RS7BOo"
CHAT_ID = "8134864975"
SITE_URL = "https://mobbymobbym-arch.github.io/daily-curation/"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": "true",
        "parse_mode": "Markdown"
    }).encode("utf-8")
    
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode())
            if result.get("ok"):
                print("✅ Telegram 通知發送成功！")
            else:
                print(f"⚠️ Telegram 發送失敗: {result}")
    except Exception as e:
        print(f"⚠️ Telegram 請求錯誤: {e}")

def main():
    # 支援 --status 旗標：直接發送自訂訊息（用於錯誤告警）
    if "--status" in sys.argv:
        idx = sys.argv.index("--status")
        if idx + 1 < len(sys.argv):
            status_msg = sys.argv[idx + 1]
            send_telegram_message(f"{status_msg}\n👉 {SITE_URL}")
        else:
            send_telegram_message(f"⚠️ 管線發送了告警但沒有附帶訊息\n👉 {SITE_URL}")
        return

    if not os.path.exists(DAILY_NEWS_JSON):
        send_telegram_message(f"⚠️ 日報任務執行完畢，但找不到 {DAILY_NEWS_JSON}。\n👉 {SITE_URL}")
        return

    try:
        with open(DAILY_NEWS_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        techmeme = data.get('techmeme', [])
        wsj = data.get('wsj', [])
        
        msg_parts = ["✅ *今日日報已更新！*"]
        msg_parts.append("\n📰 *Techmeme 重點*：")
        for i, item in enumerate(techmeme[:5]):
            title = item.get('title_zh') or item.get('title_en', '')
            msg_parts.append(f"• {title}")
            
        msg_parts.append("\n📰 *WSJ 重點*：")
        for i, item in enumerate(wsj[:3]):
            title = item.get('title_zh') or item.get('title_en', '')
            msg_parts.append(f"• {title}")
            
        msg_parts.append(f"\n👉 {SITE_URL}")
        
        final_msg = "\n".join(msg_parts)
        send_telegram_message(final_msg)
        
    except Exception as e:
        send_telegram_message(f"⚠️ 日報發布成功，但讀取摘要時發生錯誤 ({e})\n👉 {SITE_URL}")

if __name__ == "__main__":
    main()
