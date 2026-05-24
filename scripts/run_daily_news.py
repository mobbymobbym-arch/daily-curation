import json
import html
import os
import re
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
TECHMEME_HOME_URL = 'https://www.techmeme.com/'
TECHMEME_MAIN_COLUMN_ID = 'topcol1'
TECHMEME_NEXT_COLUMN_ID = 'topcol23'
TAG_RE = re.compile(r'<[^>]+>')
TECHMEME_CITE_RE = re.compile(r'<CITE>(.*?)</CITE>', re.IGNORECASE | re.DOTALL)
TECHMEME_II_RE = re.compile(r'<DIV\s+CLASS=["\']ii["\']\s*>(.*?)</DIV>', re.IGNORECASE | re.DOTALL)
TECHMEME_ANCHOR_RE = re.compile(r'<A\b([^>]*)>(.*?)</A>', re.IGNORECASE | re.DOTALL)
TECHMEME_DIV_TAG_RE = re.compile(r'</?DIV\b[^>]*>', re.IGNORECASE | re.DOTALL)

def clean_text(text):
    """Collapse browser-style whitespace into a single readable string."""
    return re.sub(r'\s+', ' ', text or '').strip()

def parse_techmeme_source(cite_text):
    """Extract the publication name from Techmeme's cite text."""
    source = clean_text(cite_text).rstrip(':')
    if '/' in source:
        source = source.rsplit('/', 1)[-1]
    return source.strip().rstrip(':')

def strip_html(fragment):
    """Convert a small Techmeme HTML fragment to readable text."""
    fragment = re.sub(r'<br\s*/?>', ' ', fragment or '', flags=re.IGNORECASE)
    text = TAG_RE.sub(' ', fragment)
    return clean_text(html.unescape(text).replace('\xa0', ' '))

def get_attr(attrs, attr_name):
    match = re.search(rf'\b{attr_name}\s*=\s*(["\'])(.*?)\1', attrs or '', re.IGNORECASE | re.DOTALL)
    return html.unescape(match.group(2)) if match else ''

def attrs_include_class(attrs, class_name):
    class_attr = get_attr(attrs, 'class')
    return class_name in class_attr.split()

def tag_includes_class(tag, class_name):
    return attrs_include_class(tag, class_name)

def find_balanced_div_end(fragment, start_index):
    depth = 0
    for match in TECHMEME_DIV_TAG_RE.finditer(fragment, start_index):
        tag = match.group(0)
        if tag.startswith('</'):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    return len(fragment)

def iter_div_blocks_by_class(fragment, class_name):
    pos = 0
    while True:
        start_match = None
        for match in TECHMEME_DIV_TAG_RE.finditer(fragment, pos):
            tag = match.group(0)
            if tag.startswith('</') or not tag_includes_class(tag, class_name):
                continue
            start_match = match
            break

        if not start_match:
            return

        start = start_match.start()
        end = find_balanced_div_end(fragment, start)
        yield start, end, fragment[start:end]
        pos = end

def first_div_block_by_class(fragment, class_name):
    return next(iter_div_blocks_by_class(fragment, class_name), None)

def extract_techmeme_main_column_html(content):
    start_match = re.search(
        rf'<DIV\s+ID=["\']{TECHMEME_MAIN_COLUMN_ID}["\']\s*>',
        content,
        re.IGNORECASE,
    )
    end_match = re.search(
        rf'<DIV\s+ID=["\']{TECHMEME_NEXT_COLUMN_ID}["\']\s*>',
        content,
        re.IGNORECASE,
    )
    if not (start_match and end_match and start_match.end() < end_match.start()):
        return ''
    return content[start_match.end():end_match.start()]

def parse_techmeme_item_block(segment, cluster_role):
    headline_container = TECHMEME_II_RE.search(segment)
    if not headline_container:
        return None

    ii_html = headline_container.group(1)
    headline = None
    for anchor in TECHMEME_ANCHOR_RE.finditer(ii_html):
        attrs = anchor.group(1)
        if not attrs_include_class(attrs, 'ourh'):
            continue
        headline = {
            'url': urllib.parse.urljoin(TECHMEME_HOME_URL, get_attr(attrs, 'href') or '#'),
            'title_en': strip_html(anchor.group(2)),
            'summary_en': strip_html(ii_html[anchor.end():]),
        }
        break

    if not headline:
        return None

    source_html = segment[:headline_container.start()]
    source_match = TECHMEME_CITE_RE.search(source_html)
    source = parse_techmeme_source(strip_html(source_match.group(1))) if source_match else ''
    summary = re.sub(r'^(?:[-–—]\s*)+', '', headline['summary_en']).strip()
    title = headline['title_en']
    url = headline['url']

    if not (title and url and source):
        return None

    return {
        'title_en': title,
        'url': url,
        'summary_en': summary,
        'source': source,
        'media_source': source,
        'techmeme_source': 'homepage_main_column',
        'techmeme_cluster_role': cluster_role,
    }

def parse_techmeme_cluster_blocks(cluster_html):
    relitems_block = first_div_block_by_class(cluster_html, 'relitems')
    relitems_start = relitems_block[0] if relitems_block else len(cluster_html)
    main_area = cluster_html[:relitems_start]

    item_blocks = []
    main_block = first_div_block_by_class(main_area, 'itc1')
    if main_block:
        item_blocks.append((main_block[2], 'main'))

    if relitems_block:
        related_block = first_div_block_by_class(relitems_block[2], 'itc1')
        if related_block:
            item_blocks.append((related_block[2], 'related'))

    return item_blocks

def item_inside_ranges(start, ranges):
    return any(range_start <= start < range_end for range_start, range_end in ranges)

def parse_techmeme_main_column_items(content):
    """Return Techmeme main-column items, keeping only the first related item per cluster."""
    main_column_html = extract_techmeme_main_column_html(content)
    if not main_column_html:
        return []

    candidates = []
    cluster_ranges = []
    for cluster_start, cluster_end, cluster_html in iter_div_blocks_by_class(main_column_html, 'clus'):
        cluster_ranges.append((cluster_start, cluster_end))
        for item_block, cluster_role in parse_techmeme_cluster_blocks(cluster_html):
            candidates.append((cluster_start, item_block, cluster_role))

    for item_start, _item_end, item_html in iter_div_blocks_by_class(main_column_html, 'itc1'):
        if item_inside_ranges(item_start, cluster_ranges):
            continue
        candidates.append((item_start, item_html, 'main'))

    items = []
    seen = set()
    for _position, item_html, cluster_role in sorted(candidates, key=lambda row: row[0]):
        item = parse_techmeme_item_block(item_html, cluster_role)
        if not item:
            continue

        dedupe_key = (item['title_en'], item['url'])
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        items.append(item)

    return items

def fetch_url_content(url):
    """Simple fetcher with User-Agent and timeout."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"⚠️ Fetch failed for {url}: {e}")
        return ""

def fetch_rss_items(url, limit=10, extract_original_url=False, max_retries=3):
    """Parses RSS feed and returns list of items, with retries."""
    import time
    import xml.etree.ElementTree as ET
    
    for attempt in range(max_retries):
        items = []
        try:
            content = fetch_url_content(url)
            if not content:
                print(f"   ⚠️ RSS Parse Warning for {url}: Empty content (Attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(5)
                continue
            
            root = ET.fromstring(content)
            channel = root.find('channel')
            if not channel:
                print(f"   ⚠️ RSS Parse Warning for {url}: No channel found (Attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(5)
                continue
            
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
            return items # Successfully fetched and parsed
            
        except ET.ParseError as e:
            print(f"   ⚠️ RSS Parse XML Error for {url}: {e} (Attempt {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(5)
        except Exception as e:
            print(f"   ⚠️ RSS Fetch/Parse Error for {url}: {e} (Attempt {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(5)
                
    print(f"   ❌ Exhausted {max_retries} retries for {url}.")
    return []

def fetch_techmeme_main_column_items(url=TECHMEME_HOME_URL, max_retries=3):
    """Fetch Techmeme homepage and return every standalone main-column headline."""
    import time

    for attempt in range(max_retries):
        try:
            content = fetch_url_content(url)
            if not content:
                print(f"   ⚠️ Techmeme homepage empty (Attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(5)
                continue

            items = parse_techmeme_main_column_items(content)
            if items:
                return items

            print(f"   ⚠️ Techmeme homepage parser found no main-column items (Attempt {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(5)
        except Exception as e:
            print(f"   ⚠️ Techmeme homepage fetch/parse error: {e} (Attempt {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(5)

    print(f"   ❌ Exhausted {max_retries} retries for Techmeme homepage.")
    return []

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
        daily_data["fetch_date"] = str(datetime.now().date())
    else:
        daily_data = {"fetch_date": str(datetime.now().date())}

    daily_data["deep_analysis_updates"] = []

    # 1. Techmeme
    print("   ▶ Fetching Techmeme homepage main column...")
    techmeme_items = fetch_techmeme_main_column_items()
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
    Guardrail: Verify that the temporary JSON contains Chinese translations for all titles.
    Items tagged with '_translation_skipped: true' are allowed through (they have an English fallback).
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

    skipped_count = 0

    # Check Techmeme
    for item in data.get('techmeme', []):
        if item.get('_translation_skipped'):
            skipped_count += 1
            continue  # Allow items that were explicitly skipped (they have English fallback)
        if not has_chinese(item.get('title_zh')):
            print(f"❌ Missing or invalid Chinese translation for Techmeme: {item.get('title_en')}")
            return False
            
    # Check WSJ
    for item in data.get('wsj', []):
        if item.get('_translation_skipped'):
            skipped_count += 1
            continue
        if not has_chinese(item.get('title_zh')):
            print(f"❌ Missing or invalid Chinese translation for WSJ: {item.get('title_en')}")
            return False
            
    if skipped_count > 0:
        print(f"✅ Quality check passed ({skipped_count} item(s) using English fallback). Proceeding to publish.")
    else:
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

        # 5. Build evergreen section pages
        print("\n🧱 Building Section Pages...")
        section_result = subprocess.run(["python3", "scripts/build_section_pages.py"])
        if section_result.returncode != 0:
            print("🚫 Publish blocked: section pages failed to build.")
            sys.exit(section_result.returncode)

        # 6. Publish (Git Push)
        print("\n🚀 Publishing to GitHub...")
        subprocess.run(["python3", "scripts/publish.py"])
        print("\n✨ All tasks completed successfully.")
    else:
        print("\n📝 News fetched. Please perform translation before running with --publish.")

if __name__ == "__main__":
    main()
