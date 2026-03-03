import json
import os
import sys
import subprocess
import urllib.request
import urllib.parse
import ssl
from datetime import datetime

# Disable SSL verification for RSS fetching (macOS python environment fix)
ssl._create_default_https_context = ssl._create_unverified_context

# Files
DAILY_NEWS_JSON = 'daily_news_temp.json'
ANALYSIS_STATE_FILE = 'analysis_state.json'
SOURCES_FILE = 'deep_analysis_sources.json'

# Load the check module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import check_analysis_updates

def get_gemini_response(prompt, api_key):
    """
    Revised: Call OpenClaw Gateway local endpoint (OpenAI-compatible) 
    to use the agent's native model capability.
    """
    # Try to get Gateway Token and URL from env
    gateway_token = os.environ.get('OPENCLAW_GATEWAY_TOKEN')
    # Default to localhost:4000 if not set, which is standard for OpenClaw
    gateway_url = os.environ.get('OPENCLAW_GATEWAY_URL', 'http://127.0.0.1:4000')
    
    if not gateway_token:
        print("   ❌ No Gateway Token found. Skipping translation.")
        return None

    # Construct the full URL for chat completions
    # Note: Depending on how the gateway exposes it, it might be /v1/chat/completions
    url = f"{gateway_url}/v1/chat/completions"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {gateway_token}'
    }
    
    # Use 'default' model to let Gateway route to the best available one (e.g. Gemini 3.0 Pro)
    data = {
        "model": "default", 
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req) as response:
            result = json.load(response)
            # OpenAI format response
            return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"❌ Local Gateway Call Failed: {e}")
        return None

def fetch_url_content(url):
    """
    Simple fetcher. For complex sites (like WSJ), this might need a headless browser or agent intervention.
    For Substack/Stratechery feeds, simple GET often works or we use the snippet.
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"⚠️ Fetch failed for {url}: {e}")
        return ""

def process_deep_analysis_updates(api_key):
    """
    1. Check for updates
    2. If found, fetch content
    3. Generate summary using LLM
    4. Update JSON & State
    """
    print("🔍 Checking for Deep Analysis updates...")
    
    # 1. Run the check
    # We capture stdout from the check script or import its logic
    # Since we imported the module, let's look at how to use it.
    # We'll reuse the logic from check_analysis_updates.py but adapted here or call it via subprocess to get the JSON output.
    
    result = subprocess.run(
        ["python3", "scripts/check_analysis_updates.py"], 
        capture_output=True, 
        text=True
    )
    
    try:
        updates = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("⚠️ Failed to parse update check output.")
        return

    if not updates:
        print("✅ No new updates found. Skipping Deep Analysis processing.")
        return

    print(f"🚀 Found {len(updates)} new articles! Processing...")
    
    # Load existing news data
    if os.path.exists(DAILY_NEWS_JSON):
        with open(DAILY_NEWS_JSON, 'r') as f:
            daily_data = json.load(f)
    else:
        daily_data = {"deep_analysis": {}}

    if 'deep_analysis' not in daily_data:
        daily_data['deep_analysis'] = {}

    # Load state to update later
    if os.path.exists(ANALYSIS_STATE_FILE):
        with open(ANALYSIS_STATE_FILE, 'r') as f:
            state = json.load(f)
    else:
        state = {}

    for update in updates:
        source_name = update['name']
        link = update['new_link']
        title = update['title']
        prompt_type = update.get('prompt_type', 'analysis')
        
        print(f"   ▶ Processing: {source_name} - {title}")
        
        # 2. Fetch Content (Basic fetch, might need improvement for some sites)
        article_content = fetch_url_content(link)
        
        # Truncate content
        if len(article_content) > 50000:
            article_content = article_content[:50000]

        # 3. Generate Summary
        system_instruction = """
        You are a professional tech analyst (Daily News Curation Agent).
        Task: Summarize the following article in Traditional Chinese (繁體中文).
        
        Output Format (JSON):
        {
            "title": "Translated Title in Chinese",
            "title_en": "Original English Title",
            "analysis_zh": "A fluent, journalistic summary (300-500 words). Do not use bullet points here. Use <p> tags for paragraphs. Use 🌵 emoji occasionally.",
            "insights": ["Key Insight 1", "Key Insight 2", "Key Insight 3"]
        }
        
        Article:
        """
        
        prompt = f"{system_instruction}\nTitle: {title}\nLink: {link}\nContent Snippet: {article_content[:10000]}..." 
        
        if not api_key:
            # For local gateway call, we use a placeholder or None as check happens inside function
            # But the logic below passes api_key. We'll pass None and let the function check ENV.
            pass
            
        llm_response = get_gemini_response(prompt, api_key)
        
        if llm_response:
            try:
                # Clean up markdown if present
                clean_json = llm_response.replace('```json', '').replace('```', '').strip()
                parsed_response = json.loads(clean_json)
                parsed_response['url'] = link
                
                daily_data['deep_analysis'][source_name] = parsed_response
                state[source_name] = link
                print(f"   ✅ Successfully summarized {source_name}")
                
            except json.JSONDecodeError:
                print(f"   ❌ Failed to parse LLM response for {source_name}")
        else:
            print(f"   ❌ LLM returned no response for {source_name}")

    # Save updated data
    with open(DAILY_NEWS_JSON, 'w', encoding='utf-8') as f:
        json.dump(daily_data, f, indent=2, ensure_ascii=False)
        
    # Save updated state
    with open(ANALYSIS_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)

def fetch_rss_items(url, limit=10):
    """Parses RSS feed and returns list of items"""
    import xml.etree.ElementTree as ET
    items = []
    try:
        content = fetch_url_content(url)
        if not content: return []
        
        root = ET.fromstring(content)
        channel = root.find('channel')
        if not channel: return []
        
        for item in channel.findall('item')[:limit]:
            title = item.find('title').text if item.find('title') is not None else "No Title"
            link = item.find('link').text if item.find('link') is not None else "#"
            desc = item.find('description').text if item.find('description') is not None else ""
            
            # Simple metadata extraction
            # For production, might need more robust parsing (e.g., feedparser lib) but keeping it stdlib for now
            items.append({
                "title_en": title,
                "url": link,
                "summary_en": desc[:200] + "..." if desc else ""
            })
    except Exception as e:
        print(f"   ⚠️ RSS Parse Error for {url}: {e}")
    return items

def update_news_headlines(api_key):
    """
    Fetches Techmeme and WSJ (Best Effort)
    Translates titles if API key is present
    """
    print("📰 Updating News Headlines...")
    
    # Load existing data to preserve if fetch fails
    if os.path.exists(DAILY_NEWS_JSON):
        with open(DAILY_NEWS_JSON, 'r') as f:
            daily_data = json.load(f)
    else:
        daily_data = {}

    # 1. Techmeme
    print("   ▶ Fetching Techmeme...")
    techmeme_items = fetch_rss_items("https://www.techmeme.com/feed.xml", limit=15)
    
    if techmeme_items:
        # Translate Titles (Batch)
        # Always try translation now since we use local gateway
        prompt = "Translate these titles to Traditional Chinese (Taiwan). Return a JSON object where keys are indices and values are translated titles.\n"
        for i, item in enumerate(techmeme_items):
            prompt += f"{i}: {item['title_en']}\n"
        
        llm_resp = get_gemini_response(prompt, api_key)
        if llm_resp:
            try:
                translations = json.loads(llm_resp.replace('```json', '').replace('```', ''))
                for i, item in enumerate(techmeme_items):
                    if str(i) in translations:
                        item['title_zh'] = translations[str(i)]
            except:
                print("   ⚠️ Translation parsing failed")
        
        daily_data['techmeme'] = techmeme_items
        print(f"   ✅ Updated {len(techmeme_items)} Techmeme items.")
    else:
        print("   ❌ Techmeme fetch failed. Keeping existing data.")

    # 2. WSJ (RSS) - Often blocks simple requests, but let's try with User-Agent
    print("   ▶ Fetching WSJ Technology...")
    wsj_items = fetch_rss_items("https://feeds.content.dowjones.io/public/rss/RSSWSJD", limit=10)
    
    if wsj_items:
        # Translate WSJ Titles
        prompt = "Translate these titles to Traditional Chinese (Taiwan). Return a JSON object where keys are indices and values are translated titles.\n"
        for i, item in enumerate(wsj_items):
            prompt += f"{i}: {item['title_en']}\n"
        
        llm_resp = get_gemini_response(prompt, api_key)
        if llm_resp:
            try:
                translations = json.loads(llm_resp.replace('```json', '').replace('```', ''))
                for i, item in enumerate(wsj_items):
                    if str(i) in translations:
                        item['title_zh'] = translations[str(i)]
            except:
                print("   ⚠️ Translation parsing failed")

        daily_data['wsj'] = wsj_items
        print(f"   ✅ Updated {len(wsj_items)} WSJ items.")
    else:
        print("   ⚠️ WSJ fetch failed (likely 403). Keeping existing data.")

    # Save
    with open(DAILY_NEWS_JSON, 'w', encoding='utf-8') as f:
        json.dump(daily_data, f, indent=2, ensure_ascii=False)

def main():
    print("========================================")
    print(f"🤖 Daily News Curation Automation - {datetime.now()}")
    print("========================================")

    # 0. Check Environment
    # Note: With local gateway, external GEMINI_API_KEY is optional/unused, 
    # but we keep the variable for compatibility
    api_key = os.environ.get('GEMINI_API_KEY')
    
    # 1. Update Headlines (Task A1)
    update_news_headlines(api_key)

    # 2. Update Deep Analysis (Task A2)
    process_deep_analysis_updates(api_key)
    
    # 3. Render News (Task B)
    print("\n🎨 Rendering Website...")
    if subprocess.run(["python3", "scripts/render_news.py"]).returncode != 0:
        print("❌ Rendering failed.")
        sys.exit(1)

    # 3. Update Archives
    print("\n🗄️ Updating Archives...")
    subprocess.run(["python3", "scripts/update_archives.py"])

    # 4. Publish (Git Push)
    print("\n🚀 Publishing to GitHub...")
    subprocess.run(["python3", "scripts/publish.py"])
    
    print("\n✨ All tasks completed successfully.")

if __name__ == "__main__":
    main()
