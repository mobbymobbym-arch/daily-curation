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
import argparse
import urllib.request
from datetime import datetime

from gemini_key_pool import GeminiKeyPool

ssl._create_default_https_context = ssl._create_unverified_context

# --- Configuration ---
YTDLP_PATH = "yt-dlp"
JINA_PREFIX = "https://r.jina.ai/"
PODCAST_JSON = "podcast_data.json"
TEMP_DIR = "/tmp/podcast_workdir"
GEMINI_AUDIO_MAX_MB = 19.0
PODCAST_MODEL = "gemini-3-flash-preview"
GEMINI_KEYS = GeminiKeyPool()

# --- Podcast Analysis Prompt ---
PODCAST_PROMPT = """你是一位熟悉科技、創投與商業議題的台灣繁體中文 Podcast 編輯。
請仔細閱讀以下 Podcast 逐字稿/內容，並嚴格依照以下規則，產出 JSON 格式的摘要。

## 寫作規範
1. **開頭資訊**：在 summary 欄位開頭，分別各用一句話介紹這個節目/媒體，以及主持人與來賓的身份背景。
2. **核心主題 summary**：接著用 100-200 字說清楚這集主要在談什麼，以及它為什麼重要？為什麼值得了解？
3. **章節 chapters**：按時間軸，每 10-15 分鐘切成一個章節。
4. **章節內容**：每章 500-700 字，重點是清楚交代脈絡、論點、例子與商業含義。適當進行分段。每章要製作一個小標題。
5. **寫法**：使用段落式敘事，不要條列；語氣要像台灣讀者能夠順暢閱讀的商業科技分析。
6. **引用 quote**：每章節必須包含至少一處說話者原話引用，quote 保留英文。

## 語言與風格規範
1. 全文必須使用台灣繁體中文與台灣常見用語。
2. 文字風格要自然、清楚、克制，像台灣科技媒體或商業專欄的分析文章。
3. 嚴禁中國大陸慣用語、官式宣傳語、過度宏大的科技媒體腔。
4. 不要為了顯得「深度」而使用浮誇形容詞；重點是把脈絡、因果與商業意義講清楚。
5. 可以有敘事感，但不要寫成史詩、宣傳稿、投資簡報或過度戲劇化的評論。

## 用詞自我檢查
請避免使用下列中國大陸科技媒體或官式宣傳腔常見詞彙，除非是原文直接引用或不可替代的專有名詞：
揭示、前沿、戰略、深層、賦能、落地、布局、佈局、打造、生態、閉環、賽道、抓手、硬核、顛覆、穿透、底層邏輯、護城河、宏大敘事、藍圖、加持、引爆、重塑、賦予。

若遇到類似概念，請優先改用台灣讀者更自然的說法：
「揭示」改成「說明」、「點出」、「顯示」；「前沿」改成「最前線」、「最新」、「先進」；「戰略」改成「策略」、「長期規劃」、「資源配置」；「深層」改成「背後的」、「更深一層」；「打造」改成「建立」、「做出」、「發展」；「落地」改成「實際應用」、「導入」、「真的用起來」；「賦能」改成「幫助」、「讓……更容易」、「提升」。

## ⚠️ 輸出格式規範 (CRITICAL)
你必須直接輸出合法的 JSON 物件。不要有多餘文字，也不要使用 ```json 標籤。

{
  "title": "Podcast 單集標題",
  "show_name": "節目或媒體名稱",
  "summary": "先用兩句話介紹節目/媒體與主持人/來賓，再用100-200字說明本集核心主題、重要性與值得了解的原因",
  "chapters": [
    {
      "timestamp": "00:00 - 15:00",
      "title": "章節標題",
      "content": "500-700字的台灣繁體中文章節內容，可用\\n\\n分段",
      "quote": "該章節中最精彩的一句原話引用（英文）"
    }
  ]
}

## 以下為 Podcast 逐字稿/內容：
"""

TAIWAN_WORDING_REPLACEMENTS = [
    ("底層邏輯", "背後脈絡"),
    ("宏大敘事", "誇大的說法"),
    ("打造成", "發展成"),
    ("揭示", "說明"),
    ("前沿", "最前線"),
    ("戰略", "策略"),
    ("深層", "更深一層"),
    ("賦能", "幫助"),
    ("落地", "實際應用"),
    ("布局", "規劃"),
    ("佈局", "規劃"),
    ("打造", "建立"),
    ("生態", "產業環境"),
    ("閉環", "完整流程"),
    ("賽道", "市場"),
    ("抓手", "切入點"),
    ("硬核", "高門檻"),
    ("顛覆", "改變"),
    ("穿透", "看清"),
    ("護城河", "競爭優勢"),
    ("藍圖", "規劃"),
    ("加持", "幫助"),
    ("引爆", "帶動"),
    ("重塑", "改變"),
    ("賦予", "帶來"),
]


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
                "channel": info.get("channel", ""),
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

    for filename in os.listdir(TEMP_DIR):
        if filename.startswith("podcast_audio"):
            try:
                os.remove(os.path.join(TEMP_DIR, filename))
            except OSError:
                pass
    
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


def apply_taiwan_wording_guard(value, *, key=None, replacements=None):
    """Replace common non-Taiwan tech-media phrasing in generated fields."""
    if replacements is None:
        replacements = set()

    if isinstance(value, dict):
        return {
            item_key: apply_taiwan_wording_guard(
                item_value,
                key=item_key,
                replacements=replacements,
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [
            apply_taiwan_wording_guard(item, key=key, replacements=replacements)
            for item in value
        ]
    if isinstance(value, str) and key != "quote":
        cleaned = value
        for source, target in TAIWAN_WORDING_REPLACEMENTS:
            if source in cleaned:
                replacements.add(source)
                cleaned = cleaned.replace(source, target)
        return cleaned
    return value


def enforce_taiwan_wording(data):
    replacements = set()
    cleaned = apply_taiwan_wording_guard(data, replacements=replacements)
    if replacements:
        print(f"   🧹 已套用台灣用語清理：{', '.join(sorted(replacements))}")
    return cleaned


def prepare_audio_for_gemini(audio_path):
    """Keep audio small enough for Gemini CLI @file ingestion."""
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if file_size_mb <= GEMINI_AUDIO_MAX_MB:
        return audio_path

    print(f"   🔧 音檔 {file_size_mb:.1f} MB 超過 Gemini CLI 限制，先壓縮成分析用音檔...")
    compressed_path = os.path.join(TEMP_DIR, "podcast_audio_gemini.mp3")

    for bitrate in ("32k", "24k", "16k"):
        cmd = [
            "ffmpeg",
            "-y",
            "-i", audio_path,
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-b:a", bitrate,
            compressed_path,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            print(f"   ⚠️ ffmpeg 壓縮逾時 ({bitrate})")
            continue

        if result.returncode != 0:
            print(f"   ⚠️ ffmpeg 壓縮失敗 ({bitrate}): {result.stderr[:200]}")
            continue

        compressed_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
        print(f"   ✅ 壓縮完成 ({bitrate}, {compressed_size_mb:.1f} MB)")
        if compressed_size_mb <= GEMINI_AUDIO_MAX_MB:
            return compressed_path

        print("   ⚠️ 壓縮後仍超過限制，改用更低 bitrate 重試...")

    print("   ❌ 無法將音檔壓到 Gemini CLI 可接受大小")
    return None


def analyze_with_gemini(text, is_audio_file=False):
    """Send text or audio to Gemini for chapter-style analysis."""
    print("   🧠 送入 Gemini 進行深度章節分析...")

    if is_audio_file:
        audio_path = prepare_audio_for_gemini(text)
        if not audio_path:
            return None

        audio_filename = os.path.basename(audio_path)
        audio_dir = os.path.dirname(audio_path)
        audio_prompt = (
            PODCAST_PROMPT
            + f"\n\n@{audio_filename}\n\n"
            + "請先轉錄並理解這個音檔，再依照上方規範輸出合法 JSON。"
        )
        cmd = [
            "gemini", "-p", audio_prompt,
            "--model", PODCAST_MODEL,
            "--output-format", "json",
            "--include-directories", audio_dir,
        ]
        stdin_payload = None
        timeout_secs = 600
    else:
        full_prompt = PODCAST_PROMPT + "\n\n" + text[:150000]  # Cap at 150k chars
        cmd = [
            "gemini", "-p", "Generate JSON only as instructed.",
            "--model", PODCAST_MODEL,
            "--output-format", "json",
        ]
        stdin_payload = full_prompt
        timeout_secs = 300

    max_attempts = GEMINI_KEYS.attempt_count_for_model(PODCAST_MODEL, 3)
    for attempt in range(max_attempts):
        env, key_label = GEMINI_KEYS.env_for_attempt(PODCAST_MODEL, attempt)
        print(f"   🚀 啟動 Gemini CLI 進程 (Attempt {attempt + 1}/{max_attempts}, key: {key_label})")
        proc = subprocess.Popen(
            cmd,
            stdin=None if is_audio_file else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        try:
            stdout, stderr = proc.communicate(input=stdin_payload, timeout=timeout_secs)

            if not stdout or not stdout.strip():
                print("   ⚠️ Gemini 無輸出")
                if stderr:
                    print(f"      stderr: {stderr[:200]}")
                continue

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
                    data = enforce_taiwan_wording(data)
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
                        data = enforce_taiwan_wording(data)
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
                        data = enforce_taiwan_wording(data)
                        print(f"   ✅ 分析成功！{len(data.get('chapters', []))} 個章節")
                        return data
                except json.JSONDecodeError:
                    pass

            print("   ⚠️ 無法解析 Gemini 輸出的 JSON")
            print(f"      前 300 字元: {raw[:300]}")

        except subprocess.TimeoutExpired:
            proc.kill()
            print("   ⚠️ Gemini 分析逾時")

        if attempt < max_attempts - 1:
            print("   ⏳ 改用 key pool 下一把 key 重試...")

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


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a Daily Curation podcast summary card.")
    parser.add_argument("url", help="Podcast / YouTube URL to summarize.")
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Generate and render locally without publishing to GitHub Pages.",
    )
    parser.add_argument(
        "--podcast-highlights-only",
        "--section-only",
        dest="podcast_highlights_only",
        action="store_true",
        help="Only rebuild podcast_highlights_feed.json and podcast-highlights.html; do not touch index.html or publish.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Regenerate and replace the existing item for the same cleaned URL instead of appending a new card.",
    )
    return parser.parse_args()


def rebuild_podcast_highlights_page():
    result = subprocess.run(
        ["python3", "scripts/build_section_pages.py", "--only", "podcast"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"   ✅ {result.stdout.strip()}")
        return True

    print(f"   ❌ Podcast Highlights 分頁重建失敗: {result.stderr.strip() or result.stdout.strip()}")
    return False


def main():
    args = parse_args()
    raw_url = args.url
    url = clean_url(raw_url)
    publish = not args.no_publish and not args.podcast_highlights_only
    
    print("========================================")
    print(f"🎙️ Podcast 深度摘要生成器 - {datetime.now()}")
    print("========================================")
    print(f"📎 來源: {url}")
    print()

    # --- Phase 0: Check Cache ---
    all_data = load_podcast_data()
    replacement_index = None
    existing_item = None
    for index, item in enumerate(all_data['items']):
        if item.get('original_link') == url:
            replacement_index = index
            existing_item = item
            break
    
    if existing_item:
        if args.replace_existing:
            print(f"   ♻️ 網址已存在於今日清單中，將重新生成並取代：{existing_item['title']}")
            all_data['items'].pop(replacement_index)
        else:
            print(f"   ✨ 網址已存在於今日清單中：{existing_item['title']}")
            print("   ⏭️ 跳過 AI 分析，直接執行渲染流程。")
            analysis = existing_item
    else:
        replacement_index = None

    if not existing_item or args.replace_existing:
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
        if video_info:
            show_name = video_info.get("uploader") or video_info.get("channel")
            if show_name and not analysis.get("show_name"):
                analysis["show_name"] = show_name
            if video_info.get("title") and not analysis.get("source_title"):
                analysis["source_title"] = video_info["title"]
        analysis['original_link'] = url
        analysis['generated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        # Add to collection, preserving card order when replacing an existing item.
        if replacement_index is None:
            all_data['items'].append(analysis)
        else:
            all_data['items'].insert(min(replacement_index, len(all_data['items'])), analysis)
        save_podcast_data(all_data)
        action = "取代" if replacement_index is not None else "加入"
        print(f"   ✅ 已將單集「{analysis['title']}」{action}今日清單 (目前共 {len(all_data['items'])} 篇)")
    
    # --- Phase 3: Save and Render ---
    print()
    print("💾 第三階段：渲染與部署")

    if args.podcast_highlights_only:
        print("   🎨 僅重建 podcast-highlights.html 與 podcast_highlights_feed.json...")
        if not rebuild_podcast_highlights_page():
            cleanup()
            sys.exit(1)
    else:
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
        publish_env = os.environ.copy()
        publish_env.setdefault("DAILY_CURATION_SAFE_PUBLISH", "1")
        publish_env["DAILY_CURATION_PUBLISH_KIND"] = "podcast"
        result = subprocess.run(
            ["python3", "scripts/publish.py"],
            capture_output=True, text=True,
            env=publish_env,
        )
        print(f"   {result.stdout.strip()}" if result.stdout else "")

        # Telegram Notification
        try:
            msg = f"🎙️ *Podcast 摘要更新*\n\n標題：{analysis['title']}\n位置：今日廣播精選 (第 {len(all_data['items'])} 篇)"
            subprocess.run(["python3", "scripts/notify_telegram.py", "--status", msg], check=False)
        except Exception:
            pass
    else:
        if args.podcast_highlights_only:
            print("   ⏭️ 跳過發布 (--podcast-highlights-only)")
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
