import json
import os
import sys
import subprocess
import urllib.request
import re
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
        if 'feed' in root.tag: 
             entry = root.find('atom:entry', namespaces) or root.find('{http://www.w3.org/2005/Atom}entry')
             if entry:
                 link_node = entry.find('atom:link', namespaces) or entry.find('{http://www.w3.org/2005/Atom}link')
                 link = link_node.get('href') if link_node is not None else None
                 title_node = entry.find('atom:title', namespaces) or entry.find('{http://www.w3.org/2005/Atom}title')
                 title = title_node.text if title_node is not None else "Unknown"
                 return link, title
        else: 
             channel = root.find('channel')
             if channel:
                 item = channel.find('item')
                 if item:
                     link = item.find('link').text
                     title = item.find('title').text
                     return link, title
    except Exception as e:
        return None, str(e)
    return None, "No items found"

def fetch_clean_article(url):
    """Fetch clean markdown from URL using Jina Reader API."""
    try:
        jina_url = "https://r.jina.ai/" + url
        req = urllib.request.Request(jina_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"   ⚠️ Failed to fetch full article text: {e}")
        return None

def analyze_with_ai(article_text):
    """Call Gemini CLI to generate deep analysis JSON."""
    if not os.path.exists(PROMPT_FILE):
        print(f"   ⚠️ {PROMPT_FILE} not found.")
        return None
        
    with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
        prompt_base = f.read()

    full_text = prompt_base + "\n\n=== ARTICLE TEXT ===\n" + article_text

    try:
        env = os.environ.copy()
        env['NODE_TLS_REJECT_UNAUTHORIZED'] = '0'
        proc = subprocess.Popen(
            ["gemini", "-p", "Generate JSON only as instructed.", "--model", "gemini-3-flash-preview", "--output-format", "json"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        stdout, stderr = proc.communicate(input=full_text, timeout=120)

        # Parse the JSON shell from gemini CLI
        cli_response = json.loads(stdout)
        ai_output = cli_response.get("response", "")
        
        # Extract actual JSON from AI response
        match = re.search(r'\{.*\}', ai_output, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            print("   ⚠️ Failed to extract JSON from AI response:")
            print(ai_output[:200] + "...")
            return None
    except subprocess.TimeoutExpired:
        print("   ⚠️ AI Analysis timed out.")
        return None
    except Exception as e:
        print(f"   ⚠️ AI Analysis failed: {e}")
        return None

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
        last_link = state.get(name)

        print(f"▶ Polling {name}...")
        link, title = get_latest_rss_item(rss)

        if not link or not link.startswith('http'):
            print(f"   ⚠️ Invalid link or failed to fetch RSS: {title}")
            continue

        normalized_link = link.rstrip('/')
        normalized_last = last_link.rstrip('/') if last_link else None

        if normalized_link == normalized_last:
            print(f"   ✅ No new articles. Skipping.")
            continue

        print(f"   🆕 NEW ARTICLE DETECTED: {title}")
        print(f"   📥 Fetching full text via Jina...")
        article_text = fetch_clean_article(link)

        if not article_text:
            continue

        print(f"   🧠 Sending {len(article_text)} chars to AI for Deep Analysis...")
        analysis_result = analyze_with_ai(article_text)

        if analysis_result and "analysis_zh" in analysis_result and "insights" in analysis_result:
            print(f"   ✅ Analysis successful! ({len(analysis_result['analysis_zh'])} chars)")
            
            # Use data from AI response if available, fallback to RSS/config
            final_title = analysis_result.get("title") or analysis_result.get("title_zh") or title
            final_source = analysis_result.get("source") or name

            # Save to daily JSON using the structure expected by render_news.py
            daily_data["deep_analysis"][name] = {
                "title": final_title,
                "source": final_source,
                "url": link,
                "analysis_zh": analysis_result["analysis_zh"],
                "insights": analysis_result["insights"]
            }
            
            # Update state
            state[name] = normalized_link
            updates_processed += 1
        else:
            print("   ❌ AI failed to generate valid analysis format.")

    # Save outputs if anything was updated
    if updates_processed > 0:
        with open(NEWS_JSON, 'w', encoding='utf-8') as f:
            json.dump(daily_data, f, ensure_ascii=False, indent=2)
        
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            
        print(f"\n🎉 Processed {updates_processed} new deep analyses.")
        
        # Trigger render
        print("🎨 Triggering render_news.py...")
        subprocess.run(["python3", "scripts/render_news.py"])
    else:
        print("\n✅ All sources up to date.")

if __name__ == "__main__":
    main()