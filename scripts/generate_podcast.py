#!/usr/bin/env python3
"""
🎙️ Podcast 深度摘要生成器
用法: python3 scripts/generate_podcast.py "https://youtube.com/watch?v=xxx"

流程:
1. 從 YouTube 抓取逐字稿 (yt-dlp)，若失敗則用 Jina Reader 抓文字
2. 呼叫 Gemini CLI 進行章節式深度敘事分析 (繁中)
3. 輸出到 podcast_data.json
4. 呼叫 render_podcast.py 注入 HTML
5. 呼叫 publish.py 部署
"""

import json
import os
import sys
import subprocess
import re
import ssl
import urllib.request
from datetime import datetime

ssl._create_default_https_context = ssl._create_unverified_context

# --- Configuration ---
YTDLP_PATH = "yt-dlp"
JINA_PREFIX = "https://r.jina.ai/"
PODCAST_JSON = "podcast_data.json"
TEMP_DIR = "/tmp/podcast_workdir"

# --- Podcast Analysis Prompt ---
PODCAST_PROMPT = """你是一位頂尖的科技 Podcast 深度分析師與敘事型專欄作家。
請仔細閱讀以下 Podcast 逐字稿/內容，並嚴格依照以下規則，產出 JSON 格式的深度摘要。

## 寫作規範
1. **開頭資訊**：主持人與來賓各用一句話介紹身份背景。
2. **核心主題 (summary)**：50-100 字繁體中文深度主題摘要。
3. **時空切割 (chapters)**：按時間軸，每 10-15 分鐘切割一個章節。
4. **內容深度**：單一章節需達 500-700 字繁體中文。務必追求最高範圍。
5. **報導風格**：使用流暢報導文學風格，禁止條列式。
6. **細節引用**：每章節必須包含至少一處說話者的原話引用 (quote)。

## ⚠️ 輸出格式規範 (CRITICAL)
你必須直接輸出合法的 JSON 物件。不要有多餘文字，也不要使用 ```json 標籤。

{
  "title": "Podcast 中英文標題",
  "summary": "50-100字的繁中核心主題摘要",
  "chapters": [
    {
      "timestamp": "00:00 - 15:00",
      "title": "章節標題",
      "content": "500-700字的繁中章節深度敘事",
      "quote": "該章節中最精彩的一句原話引用（英文）"
    }
  ]
}

## 以下為 Podcast 逐字稿/內容：
"""


def clean_url(url):
    """移除 URL 中容易變動的追蹤參數 (如 access_token, utm_*, t, si)"""
    if not url: return url
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        filtered_query = {k: v for k, v in query.items() if not k.startswith('utm_') and k not in ('access_token', 'si', 't')}
        new_query = urllib.parse.urlencode(filtered_query, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=new_query)).rstrip('/')
    except:
        return url.rstrip('/')

def ensure_temp_dir():
    os.makedirs(TEMP_DIR, exist_ok=True)


def fetch_youtube_transcript(url):
    """Strategy A: Use yt-dlp to get YouTube subtitles/transcript."""
    print("   📹 策略 A：嘗試從 YouTube 抓取逐字稿...")
    ensure_temp_dir()
    
    sub_file = os.path.join(TEMP_DIR, "transcript")
    
    # Try auto-generated subtitles first, then manual subs
    cmd = [
        YTDLP_PATH,
        "--skip-download",
        "--no-check-certificates",
        "--write-auto-sub",
        "--write-sub",
        "--sub-lang", "en,zh-Hant,zh-Hans,zh",
        "--sub-format", "vtt/srt/best",
        "--convert-subs", "srt",
        "-o", sub_file,
        url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        # Find the generated subtitle file
        for ext in ['.en.srt', '.zh-Hant.srt', '.zh-Hans.srt', '.zh.srt', '.srt']:
            candidate = sub_file + ext
            if os.path.exists(candidate):
                with open(candidate, 'r', encoding='utf-8') as f:
                    raw = f.read()
                # Strip SRT formatting (timestamps, sequence numbers)
                lines = []
                for line in raw.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    if re.match(r'^\d+$', line):
                        continue
                    if re.match(r'\d{2}:\d{2}:\d{2}', line):
                        continue
                    # Remove HTML-like tags
                    line = re.sub(r'<[^>]+>', '', line)
                    if line:
                        lines.append(line)
                transcript = ' '.join(lines)
                print(f"   ✅ 成功抓取逐字稿 ({len(transcript)} 字元)")
                return transcript
        
        # Also check for .vtt files
        for ext in ['.en.vtt', '.zh-Hant.vtt', '.zh-Hans.vtt', '.zh.vtt', '.vtt']:
            candidate = sub_file + ext
            if os.path.exists(candidate):
                with open(candidate, 'r', encoding='utf-8') as f:
                    raw = f.read()
                lines = []
                for line in raw.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
                        continue
                    if re.match(r'\d{2}:\d{2}:\d{2}', line):
                        continue
                    line = re.sub(r'<[^>]+>', '', line)
                    if line:
                        lines.append(line)
                transcript = ' '.join(lines)
                print(f"   ✅ 成功抓取逐字稿 ({len(transcript)} 字元)")
                return transcript
        
        print(f"   ⚠️ yt-dlp 執行完成但未找到字幕檔案")
        if result.stderr:
            print(f"      stderr: {result.stderr[:200]}")
        return None
        
    except subprocess.TimeoutExpired:
        print("   ⚠️ yt-dlp 逾時")
        return None
    except Exception as e:
        print(f"   ⚠️ yt-dlp 錯誤: {e}")
        return None


def fetch_youtube_info(url):
    """Get video title and duration from YouTube."""
    cmd = [YTDLP_PATH, "--dump-json", "--skip-download", "--no-check-certificates", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            info = json.loads(result.stdout)
            return {
                "title": info.get("title", ""),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", ""),
                "description": info.get("description", "")[:500]
            }
    except Exception:
        pass
    return None


def download_and_transcribe_audio(url):
    """Strategy B: Download audio and transcribe with Whisper via Gemini."""
    print("   🎵 策略 B：嘗試下載音檔並分析...")
    ensure_temp_dir()
    audio_file = os.path.join(TEMP_DIR, "podcast_audio.mp3")
    
    # Try yt-dlp for audio download (works with YouTube, Spotify embeds, etc.)
    cmd = [
        YTDLP_PATH,
        "-x", "--audio-format", "mp3",
        "--audio-quality", "5",
        "--no-check-certificates",
        "-o", audio_file,
        url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        # Find the output file (yt-dlp may change the extension)
        for f in os.listdir(TEMP_DIR):
            if f.startswith("podcast_audio") and (f.endswith(".mp3") or f.endswith(".m4a") or f.endswith(".opus")):
                audio_path = os.path.join(TEMP_DIR, f)
                file_size = os.path.getsize(audio_path) / (1024 * 1024)
                print(f"   ✅ 音檔下載完成 ({file_size:.1f} MB)")
                
                # Use Gemini CLI to transcribe + analyze in one shot
                return audio_path
        
        print("   ⚠️ 音檔下載失敗")
        return None
                
    except Exception as e:
        print(f"   ⚠️ 音檔下載錯誤: {e}")
        return None


def fetch_via_jina(url):
    """Strategy C: Use Jina Reader to fetch page text."""
    print("   🌐 策略 C：使用 Jina Reader 抓取頁面文字...")
    jina_url = JINA_PREFIX + url
    try:
        req = urllib.request.Request(jina_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode('utf-8')
        if len(text) > 500:
            print(f"   ✅ Jina 抓取成功 ({len(text)} 字元)")
            return text
        else:
            print("   ⚠️ Jina 抓取的文字太少")
            return None
    except Exception as e:
        print(f"   ⚠️ Jina 錯誤: {e}")
        return None


def analyze_with_gemini(text, is_audio_file=False):
    """Send text or audio to Gemini for chapter-style analysis."""
    print("   🧠 送入 Gemini 進行深度章節分析...")
    
    env = os.environ.copy()
    env['NODE_TLS_REJECT_UNAUTHORIZED'] = '0'
    
    if is_audio_file:
        # For audio files, pass the file path to gemini with instruction
        audio_prompt = PODCAST_PROMPT + "\n\n[Audio file attached - please transcribe and analyze]"
        cmd = [
            "gemini", "-p", audio_prompt,
            "--model", "gemini-3.1-pro-preview",
            "--output-format", "json",
            "-f", text  # text is actually the audio file path here
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
    else:
        full_prompt = PODCAST_PROMPT + "\n\n" + text[:150000]  # Cap at 150k chars
        proc = subprocess.Popen(
            ["gemini", "-p", "Generate JSON only as instructed.",
             "--model", "gemini-3.1-pro-preview",
             "--output-format", "json"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
    
    try:
        if is_audio_file:
            stdout, stderr = proc.communicate(timeout=600)
        else:
            stdout, stderr = proc.communicate(input=full_prompt, timeout=300)
        
        if not stdout or not stdout.strip():
            print(f"   ⚠️ Gemini 無輸出")
            if stderr:
                print(f"      stderr: {stderr[:200]}")
            return None
        
        # Try to parse JSON from output
        raw = stdout.strip()
        
        # Handle Gemini CLI's session envelope: {"session_id": ..., "response": "..."}
        try:
            envelope = json.loads(raw)
            if 'response' in envelope and isinstance(envelope['response'], str):
                raw = envelope['response'].strip()
        except (json.JSONDecodeError, TypeError):
            pass
        
        # Try direct parse
        try:
            data = json.loads(raw)
            if 'title' in data and 'chapters' in data:
                print(f"   ✅ 分析成功！{len(data.get('chapters', []))} 個章節")
                return data
        except json.JSONDecodeError:
            pass
        
        # Try extracting JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', raw)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if 'title' in data:
                    print(f"   ✅ 分析成功！{len(data.get('chapters', []))} 個章節")
                    return data
            except json.JSONDecodeError:
                pass
        
        # Try finding first { to last }
        first_brace = raw.find('{')
        last_brace = raw.rfind('}')
        if first_brace >= 0 and last_brace > first_brace:
            try:
                data = json.loads(raw[first_brace:last_brace + 1])
                if 'title' in data:
                    print(f"   ✅ 分析成功！{len(data.get('chapters', []))} 個章節")
                    return data
            except json.JSONDecodeError:
                pass
        
        print(f"   ⚠️ 無法解析 Gemini 輸出的 JSON")
        print(f"      前 300 字元: {raw[:300]}")
        return None
        
    except subprocess.TimeoutExpired:
        proc.kill()
        print("   ⚠️ Gemini 分析逾時")
        return None


def cleanup():
    """Remove temporary files."""
    import shutil
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        print("   🧹 已清理暫存檔案")


def load_podcast_data():
    """Load the accumulator JSON."""
    today = datetime.now().strftime('%Y-%m-%d')
    if os.path.exists(PODCAST_JSON):
        try:
            with open(PODCAST_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # If it's a legacy format (not a dict with 'date' and 'items')
                if not isinstance(data, dict) or 'items' not in data:
                    return {"date": today, "items": []}
                # If it's a new day, we should technically archive the old one, 
                # but render_podcast.py handles the HTML archiving. 
                # We just reset the 'today' list.
                if data.get("date") != today:
                    print(f"   📅 偵測到新的一天 (之前是 {data.get('date')})，重置當日清單。")
                    return {"date": today, "items": []}
                return data
        except Exception:
            pass
    return {"date": today, "items": []}


def save_podcast_data(data):
    """Save the accumulator JSON."""
    with open(PODCAST_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    if len(sys.argv) < 2:
        print("用法: python3 scripts/generate_podcast.py <podcast_url>")
        print("範例: python3 scripts/generate_podcast.py 'https://youtube.com/watch?v=xxx'")
        sys.exit(1)
    
    raw_url = sys.argv[1]
    url = clean_url(raw_url)
    publish = "--no-publish" not in sys.argv
    
    print("========================================")
    print(f"🎙️ Podcast 深度摘要生成器 - {datetime.now()}")
    print("========================================")
    print(f"📎 來源: {url}")
    print()

    # --- Phase 0: Check Cache ---
    all_data = load_podcast_data()
    existing_item = next((item for item in all_data['items'] if item['original_link'] == url), None)
    
    if existing_item:
        print(f"   ✨ 網址已存在於今日清單中：{existing_item['title']}")
        print("   ⏭️ 跳過 AI 分析，直接執行渲染流程。")
        analysis = existing_item
    else:
        # --- Phase 1: Acquire transcript ---
        print("📥 第一階段：素材獲取")
        
        transcript = None
        video_info = None
        audio_path = None
        
        # Check if it's a YouTube URL
        is_youtube = 'youtube.com' in url or 'youtu.be' in url
        
        if is_youtube:
            video_info = fetch_youtube_info(url)
            if video_info:
                print(f"   📋 標題: {video_info['title']}")
                duration_min = video_info['duration'] // 60
                print(f"   ⏱️ 長度: {duration_min} 分鐘")
            
            # Strategy A: YouTube subtitles
            transcript = fetch_youtube_transcript(url)
        
        if not transcript:
            # Strategy B: Download audio for Gemini analysis
            audio_path = download_and_transcribe_audio(url)
        
        if not transcript and not audio_path:
            # Strategy C: Jina Reader text extraction
            transcript = fetch_via_jina(url)
        
        if not transcript and not audio_path:
            print("❌ 所有素材獲取策略均失敗。無法繼續。")
            cleanup()
            sys.exit(1)
        
        # --- Phase 2: AI Analysis ---
        print()
        print("🧠 第二階段：深度敘事分析")
        
        if audio_path:
            analysis = analyze_with_gemini(audio_path, is_audio_file=True)
        else:
            analysis = analyze_with_gemini(transcript, is_audio_file=False)
        
        if not analysis:
            print("❌ AI 分析失敗。")
            cleanup()
            sys.exit(1)
        
        # Enrich with video info
        if video_info and not analysis.get('title'):
            analysis['title'] = video_info['title']
        analysis['original_link'] = url
        analysis['generated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        # Add to collection
        all_data['items'].append(analysis)
        save_podcast_data(all_data)
        print(f"   ✅ 已將新單集「{analysis['title']}」加入今日清單 (目前共 {len(all_data['items'])} 篇)")
    
    # --- Phase 3: Save and Render ---
    print()
    print("💾 第三階段：發布與部署")
    
    # Render to HTML (surgical injection - only touches PODCAST_HIGHLIGHTS block)
    print("   🎨 執行 render_podcast.py (全量重新渲染今日卡片)...")
    result = subprocess.run(
        ["python3", "scripts/render_podcast.py"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"   ✅ {result.stdout.strip()}")
    else:
        print(f"   ⚠️ 渲染警告: {result.stderr[:200] if result.stderr else result.stdout[:200]}")
    
    # Publish to GitHub
    if publish:
        print("   🚀 執行 publish.py...")
        result = subprocess.run(
            ["python3", "scripts/publish.py"],
            capture_output=True, text=True
        )
        print(f"   {result.stdout.strip()}" if result.stdout else "")

        # Telegram Notification
        try:
            msg = f"🎙️ *Podcast 摘要更新*\n\n標題：{analysis['title']}\n位置：今日廣播精選 (第 {len(all_data['items'])} 篇)"
            subprocess.run(["python3", "scripts/notify_telegram.py", msg], check=False)
        except Exception:
            pass
    else:
        print("   ⏭️ 跳過發布 (--no-publish)")
    
    # Cleanup temp files
    cleanup()
    
    print()
    print("✨ Podcast 摘要生成完成！")
    if publish:
        print("🌐 https://mobbymobbym-arch.github.io/daily-curation/")


if __name__ == "__main__":
    main()
