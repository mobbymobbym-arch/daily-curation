import json
import os
import sys
import signal
import subprocess
import urllib.request
import urllib.parse
import re
import time
from datetime import datetime
import xml.etree.ElementTree as ET
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

SOURCES_FILE = 'deep_analysis_sources.json'
STATE_FILE = 'analysis_state.json'
NEWS_JSON = 'daily_news_temp.json'
PROMPT_FILE = 'deep_analysis_prompt.md'

def get_latest_rss_item(rss_url):
    """Fetch the latest item from an RSS feed."""
    try:
        req = urllib.request.Request(
            rss_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_content = response.read()
            
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            content_str = xml_content.decode('utf-8', errors='ignore')
            if '<item>' in content_str:
                start_link = content_str.find('<link>') + 6
                end_link = content_str.find('</link>', start_link)
                link = content_str[start_link:end_link].strip()
                if '<![CDATA[' in link:
                    link = link.replace('<![CDATA[', '').replace(']]>', '')
                return link, "Title Unknown (String Parse)"
            return None, "Parse Error"

        namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
        if root is not None and 'feed' in root.tag: 
             entry = root.find('atom:entry', namespaces) or root.find('{http://www.w3.org/2005/Atom}entry')
             if entry is not None:
                 link_node = entry.find('atom:link', namespaces) or entry.find('{http://www.w3.org/2005/Atom}link')
                 link = link_node.get('href') if link_node is not None else None
                 title_node = entry.find('atom:title', namespaces) or entry.find('{http://www.w3.org/2005/Atom}title')
                 title = title_node.text if title_node is not None else "Unknown"
                 return link, title
        else: 
             channel = root.find('channel')
             if channel is not None:
                 item = channel.find('item')
                 if item is not None:
                     link_elem = item.find('link')
                     title_elem = item.find('title')
                     link = link_elem.text if link_elem is not None else None
                     title = title_elem.text if title_elem is not None else None
                     return link, title
    except Exception as e:
        return None, str(e)
    return None, "No items found"

def fetch_clean_article(url, max_retries=3):
    """Fetch clean markdown from URL using Jina Reader API with retries."""
    import time
    for attempt in range(max_retries):
        try:
            jina_url = "https://r.jina.ai/" + url
            req = urllib.request.Request(jina_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"   ⚠️ Jina API fetch failed for {url}: {e} (Attempt {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(5)
    return None

def analyze_with_ai(article_text, max_retries=2):
    """Call Gemini CLI to generate deep analysis JSON with retries."""
    import time
    if not os.path.exists(PROMPT_FILE):
        print(f"   ⚠️ {PROMPT_FILE} not found.")
        return None
        
    with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
        prompt_base = f.read()

    full_text = prompt_base + "\n\n=== ARTICLE TEXT ===\n" + article_text

    for attempt in range(max_retries):
        proc = None
        try:
            env = os.environ.copy()
            env['NODE_TLS_REJECT_UNAUTHORIZED'] = '0'
            print(f"   🚀 啟動 Gemini CLI 進程 (Attempt {attempt+1}/{max_retries})...")
            proc = subprocess.Popen(
                ["gemini", "-p", "Generate JSON only as instructed.", "--model", "gemini-3-flash-preview", "--output-format", "json"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                start_new_session=True
            )
            print(f"   📡 已送出請求 (PID: {proc.pid})，等待回應 (上限 120s)...")
            stdout, stderr = proc.communicate(input=full_text, timeout=120)
            print(f"   📥 收到回應 ({len(stdout)} chars)，開始解析...")

            # Parse the JSON shell from gemini CLI
            try:
                cli_response = json.loads(stdout)
                ai_output = cli_response.get("response", stdout)
            except json.JSONDecodeError:
                ai_output = stdout
            
            # Extract actual JSON from AI response
            match = re.search(r'\{.*\}', ai_output, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            else:
                print("   ⚠️ Failed to extract JSON from AI response:")
                print(ai_output[:200] + "...")
                
        except subprocess.TimeoutExpired:
            print("   ⚠️ AI Analysis timed out — 終止進程組...")
        except Exception as e:
            print(f"   ⚠️ AI Analysis failed: {e}")
            
        if proc:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                proc.kill()
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
                
        if attempt < max_retries - 1:
            print("   ⏳ Retrying in 5 seconds...")
            time.sleep(5)
            
    print("   ❌ Exhausted all AI retries.")
    return None

def clean_url(url):
    """移除 URL 中容易變動的追蹤參數 (如 access_token, utm_*)"""
    if not url: return url
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        # 移除 access_token, utm_ 開頭的參數
        filtered_query = {k: v for k, v in query.items() if not k.startswith('utm_') and k != 'access_token'}
        new_query = urllib.parse.urlencode(filtered_query, doseq=True)
        return urllib.parse.urlunparse(parsed._replace(query=new_query)).rstrip('/')
    except:
        return url.rstrip('/')

def main():
    print("========================================")
    print(f"🤖 Automated Deep Analysis Generator - {datetime.now()}")
    print("========================================")

    if not os.path.exists(SOURCES_FILE):
        print(f"❌ {SOURCES_FILE} not found.")
        return

    with open(SOURCES_FILE, 'r') as f:
        sources_config = json.load(f)
    
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)

    # Initialize or load daily news temp
    if os.path.exists(NEWS_JSON):
        with open(NEWS_JSON, 'r', encoding='utf-8') as f:
            daily_data = json.load(f)
    else:
        daily_data = {"fetch_date": str(datetime.now().date()), "deep_analysis": {}}

    if "deep_analysis" not in daily_data:
        daily_data["deep_analysis"] = {}

    updates_processed = 0

    for source in sources_config['sources']:
        name = source['name']
        rss = source['rss']
        cached_info = state.get(name)

        print(f"▶ Polling {name}...")
        raw_link, raw_title = get_latest_rss_item(rss)

        if not raw_link or not raw_link.startswith('http'):
            print(f"   ⚠️ Invalid link or failed to fetch RSS: {raw_title}")
            continue

        cleaned_link = clean_url(raw_link)
        
        # 判斷是否為舊文章 (判斷依據：URL 或 原始標題 相符)
        is_old_article = False
        cached_content = None
        
        if isinstance(cached_info, dict):
            cached_url = cached_info.get("url")
            cached_title = cached_info.get("title")
            cached_content = cached_info.get("content")
            if cleaned_link == cached_url or raw_title == cached_title:
                is_old_article = True
        elif isinstance(cached_info, str):
            # 兼容舊版 state 格式 (只存 URL 字串)
            if cleaned_link == clean_url(cached_info):
                is_old_article = True

        if is_old_article:
            print(f"   ✅ No new articles (Matched: {raw_title}).")
            # 如果快取有完整內容，直接復用，不呼叫 AI
            if cached_content:
                daily_data["deep_analysis"][name] = cached_content
                # 如果今天還沒存進 temp，就標記更新以便觸發渲染
                # (但不用重寫 state)
                updates_processed += 1
                with open(NEWS_JSON, 'w', encoding='utf-8') as f:
                    json.dump(daily_data, f, ensure_ascii=False, indent=2)
            continue

        print(f"   🆕 NEW ARTICLE DETECTED: {raw_title}")
        print(f"   📥 Fetching full text via Jina...")
        article_text = fetch_clean_article(raw_link)

        if not article_text:
            continue

        print(f"   🧠 Sending {len(article_text)} chars to AI for Deep Analysis...")
        analysis_result = analyze_with_ai(article_text)

        if analysis_result and "analysis_zh" in analysis_result and "insights" in analysis_result:
            print(f"   ✅ Analysis successful! ({len(analysis_result['analysis_zh'])} chars)")
            
            # Use data from AI response if available, fallback to RSS
            final_title = analysis_result.get("title") or analysis_result.get("title_zh") or raw_title
            final_source = analysis_result.get("source") or name

            content_to_save = {
                "title": final_title,
                "source": final_source,
                "url": raw_link,
                "analysis_zh": analysis_result["analysis_zh"],
                "insights": analysis_result["insights"]
            }

            daily_data["deep_analysis"][name] = content_to_save
            
            # Update state with new dictionary format for robust caching
            state[name] = {
                "url": cleaned_link,
                "title": raw_title,
                "content": content_to_save
            }
            updates_processed += 1

            # ⚡ Incremental save
            with open(NEWS_JSON, 'w', encoding='utf-8') as f:
                json.dump(daily_data, f, ensure_ascii=False, indent=2)
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            print(f"   💾 Progress saved.")
        else:
            print("   ❌ AI failed to generate valid analysis format.")

    if updates_processed > 0:
        print(f"\n🎉 Processed {updates_processed} new deep analyses.")
        # Trigger render
        print("🎨 Triggering render_news.py...")
        subprocess.run(["python3", "scripts/render_news.py"])
    else:
        print("\n✅ All sources up to date.")

if __name__ == "__main__":
    main()