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
INDEX_HTML = 'index.html'
TECHMEME_HOME_URL = 'https://www.techmeme.com/'
TECHMEME_RSS_URL = 'https://www.techmeme.com/feed.xml'
WSJ_TECH_RSS_URL = 'https://feeds.content.dowjones.io/public/rss/RSSWSJD'
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

def normalize_match_url(url):
    """Normalize URLs enough to match an RSS/article URL across sources."""
    if not url:
        return ''
    try:
        parsed = urllib.parse.urlparse(html.unescape(str(url)).strip())
        query = [
            (key, value)
            for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            if not key.startswith('utm_') and key not in {'mod', 'st', 'reflink'}
        ]
        return urllib.parse.urlunparse(
            parsed._replace(query=urllib.parse.urlencode(query, doseq=True), fragment='')
        ).rstrip('/')
    except Exception:
        return html.unescape(str(url)).strip().rstrip('/')

def extract_image_url_from_fragment(fragment, base_url=TECHMEME_HOME_URL):
    """Extract the first non-sponsored image from a small HTML fragment."""
    for img_match in re.finditer(r'<IMG\b([^>]*)>', fragment or '', re.IGNORECASE | re.DOTALL):
        src = get_attr(img_match.group(1), 'src')
        if not src:
            continue
        resolved = urllib.parse.urljoin(base_url, src)
        if '/simg/' in resolved:
            continue
        return resolved.replace('http://www.techmeme.com/', 'https://www.techmeme.com/')
    return ''

def set_image_fields(item, image_url, image_source, image_credit='', image_alt=''):
    if not image_url:
        return item
    item['image_url'] = image_url
    item['image_source'] = image_source
    if image_credit:
        item['image_credit'] = image_credit
    item['image_alt'] = image_alt or item.get('title_en') or ''
    return item

def set_thumbnail_fields(item, image_url, image_source, image_credit='', image_alt=''):
    if not image_url:
        return item
    item['thumbnail_url'] = image_url
    item['thumbnail_source'] = image_source
    if image_credit:
        item['thumbnail_credit'] = image_credit
    item['thumbnail_alt'] = image_alt or item.get('title_en') or ''
    return item

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

    image_url = extract_image_url_from_fragment(ii_html)
    source_html = segment[:headline_container.start()]
    source_match = TECHMEME_CITE_RE.search(source_html)
    source = parse_techmeme_source(strip_html(source_match.group(1))) if source_match else ''
    summary = re.sub(r'^(?:[-–—]\s*)+', '', headline['summary_en']).strip()
    title = headline['title_en']
    url = headline['url']

    if not (title and url and source):
        return None

    item = {
        'title_en': title,
        'url': url,
        'summary_en': summary,
        'source': source,
        'media_source': source,
        'techmeme_source': 'homepage_main_column',
        'techmeme_cluster_role': cluster_role,
    }
    return set_thumbnail_fields(item, image_url, 'techmeme_story_block', image_credit='Techmeme')

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

def extract_article_meta_image(url):
    """Last-resort image fallback from og:image/twitter:image metadata."""
    content = fetch_url_content(url)
    if not content:
        return ''

    image_keys = {'og:image', 'twitter:image', 'og:image:url'}
    for meta_match in re.finditer(r'<meta\b([^>]*)>', content, re.IGNORECASE | re.DOTALL):
        attrs = meta_match.group(1)
        key = (get_attr(attrs, 'property') or get_attr(attrs, 'name')).lower()
        if key not in image_keys:
            continue
        image_url = get_attr(attrs, 'content').strip()
        if image_url:
            return image_url
    return ''

def techmeme_rss_image_lookup():
    """Build a URL -> Techmeme thumbnail map from the public RSS description HTML."""
    import xml.etree.ElementTree as ET

    content = fetch_url_content(TECHMEME_RSS_URL)
    if not content:
        return {}

    lookup = {}
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return lookup

    channel = root.find('channel')
    if channel is None:
        return lookup

    for item in channel.findall('item'):
        desc = item.findtext('description') or ''
        match = re.search(
            r'<A\b[^>]*\bHREF=(["\'])(.*?)\1[^>]*>\s*<IMG\b([^>]*)>',
            desc,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            continue
        article_url = html.unescape(match.group(2)).strip()
        image_url = extract_image_url_from_fragment(match.group(0), base_url=TECHMEME_HOME_URL)
        if article_url and image_url:
            lookup[normalize_match_url(article_url)] = image_url
    return lookup

def ensure_lead_image(items, source_name, lookup=None):
    """Ensure the first card has an image using cheap source-specific fallbacks."""
    if not items:
        return

    lead = items[0]
    if lead.get('image_url'):
        return

    normalized_url = normalize_match_url(lead.get('url'))
    if lookup and normalized_url in lookup:
        set_thumbnail_fields(lead, lookup[normalized_url], f'{source_name}_rss_thumbnail')

    meta_image = extract_article_meta_image(lead.get('url') or '')
    if meta_image:
        set_image_fields(lead, meta_image, 'article_meta_fallback')
    else:
        lead['image_missing_reason'] = 'no_source_image_found'

def copy_image_fields(target, source):
    """Copy only image-related metadata between matching headline records."""
    changed = False
    if not target or not source:
        return changed

    if source.get('image_url') and target.pop('image_missing_reason', None) is not None:
        changed = True

    for field in (
        'image_url',
        'image_source',
        'image_credit',
        'image_alt',
        'thumbnail_url',
        'thumbnail_source',
        'thumbnail_credit',
        'thumbnail_alt',
    ):
        value = source.get(field)
        if value and target.get(field) != value:
            target[field] = value
            changed = True
    return changed

def image_lookup_by_url(items):
    return {
        normalize_match_url(item.get('url')): item
        for item in items
        if normalize_match_url(item.get('url')) and item.get('image_url')
    }

def refresh_existing_headline_images():
    """Backfill just the two homepage lead-card images without replacing translations."""
    if not os.path.exists(DAILY_NEWS_JSON):
        print(f"❌ {DAILY_NEWS_JSON} not found; run the daily fetch first.")
        return False

    with open(DAILY_NEWS_JSON, 'r', encoding='utf-8') as f:
        daily_data = json.load(f)

    print("🖼️ Refreshing homepage lead images without changing translations...")

    techmeme_items = daily_data.get('techmeme') or []
    if techmeme_items:
        print("   ▶ Matching Techmeme lead image...")
        homepage_lookup = image_lookup_by_url(fetch_techmeme_main_column_items())
        lead_key = normalize_match_url(techmeme_items[0].get('url'))
        if lead_key in homepage_lookup:
            copy_image_fields(techmeme_items[0], homepage_lookup[lead_key])
        ensure_lead_image(techmeme_items, 'techmeme', techmeme_rss_image_lookup())
        status = techmeme_items[0].get('image_url') or techmeme_items[0].get('image_missing_reason', 'missing')
        print(f"   ✅ Techmeme lead image status: {status}")

    wsj_items = daily_data.get('wsj') or []
    if wsj_items:
        print("   ▶ Matching WSJ lead image...")
        rss_lookup = image_lookup_by_url(fetch_rss_items(WSJ_TECH_RSS_URL, limit=40))
        lead_key = normalize_match_url(wsj_items[0].get('url'))
        if lead_key in rss_lookup:
            copy_image_fields(wsj_items[0], rss_lookup[lead_key])
        ensure_lead_image(wsj_items, 'wsj')
        status = wsj_items[0].get('image_url') or wsj_items[0].get('image_missing_reason', 'missing')
        print(f"   ✅ WSJ lead image status: {status}")

    with open(DAILY_NEWS_JSON, 'w', encoding='utf-8') as f:
        json.dump(daily_data, f, indent=2, ensure_ascii=False)

    return True

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
            if channel is None:
                print(f"   ⚠️ RSS Parse Warning for {url}: No channel found (Attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(5)
                continue
            
            for item in channel.findall('item')[:limit]:
                title = item.find('title').text if item.find('title') is not None else "No Title"
                link = item.find('link').text if item.find('link') is not None else "#"
                desc = item.find('description').text if item.find('description') is not None else ""
                media = item.find('{http://search.yahoo.com/mrss/}content')
                media_url = media.attrib.get('url', '').strip() if media is not None else ''
                media_credit_node = media.find('{http://search.yahoo.com/mrss/}credit') if media is not None else None
                media_credit = clean_text(media_credit_node.text) if media_credit_node is not None else ''
                
                # For Techmeme: extract the original article URL from the description HTML
                original_url = link
                if extract_original_url and desc:
                    import re as _re
                    href_match = _re.search(r'<A\s+HREF="([^"]+)"', desc, _re.IGNORECASE)
                    if href_match:
                        original_url = href_match.group(1)
                
                row = {
                    "title_en": title,
                    "url": original_url,
                    "summary_en": desc[:200] + "..." if desc else ""
                }
                if media_url:
                    set_image_fields(row, media_url, 'rss_media_content', media_credit)
                items.append(row)
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
        if not techmeme_items[0].get('image_url'):
            ensure_lead_image(techmeme_items, 'techmeme', techmeme_rss_image_lookup())
        daily_data['techmeme'] = techmeme_items
        print(f"   ✅ Fetched {len(techmeme_items)} Techmeme items.")

    # 2. WSJ
    print("   ▶ Fetching WSJ Technology...")
    wsj_items = fetch_rss_items(WSJ_TECH_RSS_URL, limit=10)
    if wsj_items:
        ensure_lead_image(wsj_items, 'wsj')
        daily_data['wsj'] = wsj_items
        print(f"   ✅ Fetched {len(wsj_items)} WSJ items.")

    # Save raw data for agent to translate
    with open(DAILY_NEWS_JSON, 'w', encoding='utf-8') as f:
        json.dump(daily_data, f, indent=2, ensure_ascii=False)

def check_translation_quality():
    """
    Guardrail: Verify that the temporary JSON contains Chinese translations for all titles.
    Items tagged with '_translation_skipped: true' are allowed through (they have an English fallback).
    Publishing is blocked only when every fetched headline fell back to English.
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
    total_count = 0

    # Check Techmeme
    for item in data.get('techmeme', []):
        total_count += 1
        if item.get('_translation_skipped'):
            skipped_count += 1
            continue  # Allow items that were explicitly skipped (they have English fallback)
        if not has_chinese(item.get('title_zh')):
            print(f"❌ Missing or invalid Chinese translation for Techmeme: {item.get('title_en')}")
            return False
            
    # Check WSJ
    for item in data.get('wsj', []):
        total_count += 1
        if item.get('_translation_skipped'):
            skipped_count += 1
            continue
        if not has_chinese(item.get('title_zh')):
            print(f"❌ Missing or invalid Chinese translation for WSJ: {item.get('title_en')}")
            return False

    if total_count > 0 and skipped_count >= total_count:
        print(f"❌ Translation quality check failed: all {total_count} item(s) used English fallback.")
        return False

    if skipped_count > 0:
        print(f"✅ Quality check passed ({skipped_count} item(s) using English fallback). Proceeding to publish.")
    else:
        print("✅ Translation quality check passed. Proceeding to publish.")
    return True

def legacy_news_markers_present():
    """Return true only when the pre-v7 homepage renderer can safely run."""
    if not os.path.exists(INDEX_HTML):
        return False
    with open(INDEX_HTML, 'r', encoding='utf-8') as f:
        content = f.read()
    return "<!-- DAILY_NEWS_START -->" in content and "<!-- DAILY_NEWS_END -->" in content

def main():
    print("========================================")
    print(f"🤖 Daily News Curation Automation - {datetime.now()}")
    print("========================================")

    if "--refresh-images" in sys.argv:
        if not refresh_existing_headline_images():
            sys.exit(1)
        print("\n📝 Headline images refreshed. Run with --publish to rebuild and publish the site.")
        return

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

        # 3. Render legacy homepage only when the old marker-based shell is present.
        # The v7 site shell is generated later by build_site_v7.py.
        if legacy_news_markers_present():
            print("\n🎨 Rendering Legacy Homepage...")
            render_result = subprocess.run(["python3", "scripts/render_news.py"])
            if render_result.returncode != 0:
                print("🚫 Publish blocked: legacy news render failed.")
                sys.exit(render_result.returncode)
        else:
            print("\n🎨 Skipping legacy homepage renderer; v7 site shell has no DAILY_NEWS markers.")

        # 4. Update Archives
        print("\n🗄️ Updating Archives...")
        archive_result = subprocess.run(["python3", "scripts/update_archives.py"])
        if archive_result.returncode != 0:
            print("🚫 Publish blocked: archive update failed.")
            sys.exit(archive_result.returncode)

        # 5. Build evergreen section pages
        print("\n🧱 Building Section Pages...")
        section_result = subprocess.run(["python3", "scripts/build_section_pages.py"])
        if section_result.returncode != 0:
            print("🚫 Publish blocked: section pages failed to build.")
            sys.exit(section_result.returncode)

        # 6. Build the v7 production site shell from the freshly generated feeds.
        print("\n💚 Building v7 Site...")
        v7_result = subprocess.run(["python3", "scripts/build_site_v7.py"])
        if v7_result.returncode != 0:
            print("🚫 Publish blocked: v7 site failed to build.")
            sys.exit(v7_result.returncode)

        # 7. Validate external source links
        print("\n🔗 Validating External Links...")
        link_result = subprocess.run(["python3", "scripts/validate_external_links.py"])
        if link_result.returncode != 0:
            print("🚫 Publish blocked: external links must open in a new tab.")
            sys.exit(link_result.returncode)

        # 8. Publish (Git Push)
        print("\n🚀 Publishing to GitHub...")
        publish_env = os.environ.copy()
        publish_env.setdefault("DAILY_CURATION_SAFE_PUBLISH", "1")
        publish_env.setdefault("DAILY_CURATION_PUBLISH_KIND", "daily")
        publish_result = subprocess.run(["python3", "scripts/publish.py"], env=publish_env)
        if publish_result.returncode != 0:
            print("🚫 Publish blocked: GitHub publish failed.")
            sys.exit(publish_result.returncode)
        print("\n✨ All tasks completed successfully.")
    else:
        print("\n📝 News fetched. Please perform translation before running with --publish.")

if __name__ == "__main__":
    main()
