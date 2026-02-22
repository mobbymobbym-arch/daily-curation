import sys
import re
import argparse
import json
import urllib.request
import ssl
from youtube_transcript_api import YouTubeTranscriptApi

# 解決 macOS SSL 憑證問題
ssl._create_default_https_context = ssl._create_unverified_context

def extract_video_id(url_or_id):
    """從網址中精準萃取 Video ID"""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return url_or_id

def get_video_title(video_id):
    """透過簡單的網頁請求抓取 YouTube 影片的真實標題"""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read().decode('utf-8')
        # 使用正規表達式抓取 <title> 標籤內的文字
        title_match = re.search(r'<title>(.*?)</title>', html)
        if title_match:
            # 移除 YouTube 預設加上的 " - YouTube" 字尾
            return title_match.group(1).replace(" - YouTube", "").strip()
        return "未知標題"
    except Exception as e:
        return f"標題抓取失敗: {str(e)}"

def get_transcript_data(video_id):
    """核心抓取邏輯：抓取標題、抓取字幕、執行 SKILL.md 的防呆校驗"""
    result = {
        "success": False,
        "video_id": video_id,
        "title": "",
        "transcript": "",
        "validation_passed": False,
        "error_message": ""
    }
    
    # 1. 抓取標題
    title = get_video_title(video_id)
    result["title"] = title
    
    # 2. 抓取字幕
    try:
        # 修正：使用 fetch 替代 get_transcript
        api = YouTubeTranscriptApi()
        transcript_list = api.fetch(video_id)
        # 修正：FetchedTranscriptSnippet 對象應使用 .text 而非 ['text']
        full_text = " ".join([entry.text for entry in transcript_list])
        result["transcript"] = full_text.strip()
        
        # 3. 執行 SKILL.md 要求的防呆驗證
        if len(full_text) > 50:
            result["validation_passed"] = True
            result["success"] = True
        else:
            result["error_message"] = "逐字稿內容過短，可能抓取到錯誤資料。"
            
    except Exception as e:
        result["error_message"] = f"字幕抓取失敗: {str(e)}"
        
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube 逐字稿與標題抓取工具")
    parser.add_argument("--url", "-u", type=str, help="請輸入 YouTube 影片網址或 ID", required=True)
    args = parser.parse_args()
    
    real_video_id = extract_video_id(args.url)
    data = get_transcript_data(real_video_id)
    
    # 將結果輸出為 JSON 格式
    print(json.dumps(data, ensure_ascii=False, indent=2))
