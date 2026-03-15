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

def fetch_url_content(url):
    """Simple fetcher with User-Agent."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"⚠️ Fetch failed for {url}: {e}")
        return ""

def fetch_rss_items(url, limit=10, extract_original_url=False):
    """Parses RSS feed and returns list of items."""
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
            
            # For Techmeme: extract the original article URL from the description HTML
            original_url = link
            if extract_original_url and desc:
                import re as _re
                href_match = _re.search(r'<A\s+HREF="([^"]+)"', desc, _re.IGNORECASE)
                if href_match:
                    original_url = href_match.group(1)
            
            items.append({
                "title_en": title,
                "url": original_url,
                "summary_en": desc[:200] + "..." if desc else ""
            })
    except Exception as e:
        print(f"   ⚠️ RSS Parse Error for {url}: {e}")
    return items

def update_news_headlines():
    """
    Task: Fetch latest tech news.
    Translation will be performed by the agent session logic directly.
    """
    print("📰 Updating News Headlines...")
    
    # Load existing or create new
    if os.path.exists(DAILY_NEWS_JSON):
        with open(DAILY_NEWS_JSON, 'r') as f:
            daily_data = json.load(f)
    else:
        daily_data = {"fetch_date": str(datetime.now().date())}

    # 1. Techmeme
    print("   ▶ Fetching Techmeme...")
    techmeme_items = fetch_rss_items("https://www.techmeme.com/feed.xml", limit=15, extract_original_url=True)
    if techmeme_items:
        daily_data['techmeme'] = techmeme_items
        print(f"   ✅ Fetched {len(techmeme_items)} Techmeme items.")

    # 2. WSJ
    print("   ▶ Fetching WSJ Technology...")
    wsj_items = fetch_rss_items("https://feeds.content.dowjones.io/public/rss/RSSWSJD", limit=10)
    if wsj_items:
        daily_data['wsj'] = wsj_items
        print(f"   ✅ Fetched {len(wsj_items)} WSJ items.")

    # Save raw data for agent to translate
    with open(DAILY_NEWS_JSON, 'w', encoding='utf-8') as f:
        json.dump(daily_data, f, indent=2, ensure_ascii=False)

def check_translation_quality():
    """
    Strict guardrail: Verify that the temporary JSON contains 
    Chinese translations for all titles.
    """
    if not os.path.exists(DAILY_NEWS_JSON):
        print("❌ No data file found to check.")
        return False
    
    with open(DAILY_NEWS_JSON, 'r') as f:
        data = json.load(f)
    
    # Helper to detect Chinese characters
    def has_chinese(text):
        if not text: return False
        return any('\u4e00' <= char <= '\u9fff' for char in str(text))

    # Check Techmeme
    for item in data.get('techmeme', []):
        if not has_chinese(item.get('title_zh')):
            print(f"❌ Missing or invalid Chinese translation for Techmeme: {item.get('title_en')}")
            return False
            
    # Check WSJ
    for item in data.get('wsj', []):
        if not has_chinese(item.get('title_zh')):
            print(f"❌ Missing or invalid Chinese translation for WSJ: {item.get('title_en')}")
            return False
            
    print("✅ Translation quality check passed. Proceeding to publish.")
    return True

def main():
    print("========================================")
    print(f"🤖 Daily News Curation Automation - {datetime.now()}")
    print("========================================")

    # 1. Update Headlines (Raw Fetch)
    # Only fetch if we are not explicitly publishing, to avoid pulling in new untranslated items
    if "--publish" not in sys.argv:
        update_news_headlines()
    else:
        print("⏭️ Skipping fetch since --publish is active (using existing translations)...")

    # Note: At this point in a main agent session, 
    # the agent should perform translation on daily_news_temp.json 
    # before continuing to render and publish.
    # We exit here if called without --publish to allow manual/agent intervention.
    
    if "--publish" in sys.argv:
        # 2. Quality Check before Publishing
        if not check_translation_quality():
            print("🚫 Publish blocked: Incomplete translations.")
            sys.exit(1)

        # 3. Render News
        print("\n🎨 Rendering Website...")
        subprocess.run(["python3", "scripts/render_news.py"])

        # 4. Update Archives
        print("\n🗄️ Updating Archives...")
        subprocess.run(["python3", "scripts/update_archives.py"])

        # 5. Publish (Git Push)
        print("\n🚀 Publishing to GitHub...")
        subprocess.run(["python3", "scripts/publish.py"])
        print("\n✨ All tasks completed successfully.")
    else:
        print("\n📝 News fetched. Please perform translation before running with --publish.")

if __name__ == "__main__":
    main()
