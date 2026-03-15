import json
import os
import urllib.request
import xml.etree.ElementTree as ET

SOURCES_FILE = 'deep_analysis_sources.json'
STATE_FILE = 'analysis_state.json'

def get_latest_link(rss_url):
    try:
        # Use a user agent to avoid some 403s
        req = urllib.request.Request(
            rss_url, 
            data=None, 
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_content = response.read()
            
        # Try to parse XML
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            # Fallback: simple string parsing if XML is malformed or has encoding issues
            content_str = xml_content.decode('utf-8', errors='ignore')
            if '<item>' in content_str:
                # RSS-like
                start_link = content_str.find('<link>') + 6
                end_link = content_str.find('</link>', start_link)
                link = content_str[start_link:end_link].strip()
                if '<![CDATA[' in link:
                    link = link.replace('<![CDATA[', '').replace(']]>', '')
                return link, "Title Unknown (String Parse)"
            return None, "Parse Error"

        # XML Namespace handling
        namespaces = {'atom': 'http://www.w3.org/2005/Atom'}

        # Atom
        if 'feed' in root.tag: 
             entry = root.find('atom:entry', namespaces)
             if not entry:
                 entry = root.find('{http://www.w3.org/2005/Atom}entry')
             
             if entry:
                 # Atom links are often attributes
                 link_node = entry.find('atom:link', namespaces)
                 link = None
                 if link_node is not None:
                     link = link_node.get('href')
                 if not link:
                     link_node = entry.find('{http://www.w3.org/2005/Atom}link')
                     if link_node is not None:
                         link = link_node.get('href')
                 
                 title_node = entry.find('atom:title', namespaces)
                 title = "Unknown"
                 if title_node is not None:
                     title = title_node.text
                 
                 return link, title
        
        # RSS
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

def main():
    if not os.path.exists(SOURCES_FILE):
        print(json.dumps({"error": "Config file not found"}))
        return

    with open(SOURCES_FILE, 'r') as f:
        config = json.load(f)
    
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            
    updates_found = []
    
    for source in config['sources']:
        name = source['name']
        rss = source['rss']
        last_link = state.get(name)
        
        link, title_or_error = get_latest_link(rss)
        
        # Simple validation: checks if link looks like a URL
        if link and (link.startswith('http') or link.startswith('https')):
            # Normalization (some RSS feeds have trailing slashes sometimes)
            link = link.rstrip('/')
            if last_link:
                last_link = last_link.rstrip('/')

            if link != last_link:
                updates_found.append({
                    "name": name,
                    "new_link": link,
                    "title": title_or_error,
                    "prompt_type": source.get('prompt_type', 'analysis')
                })
        else:
            # Report error in a way the agent can see but doesn't break JSON
            pass 
            # print(f"[{name}] Check failed: {title_or_error}", file=sys.stderr)

    print(json.dumps(updates_found))

if __name__ == "__main__":
    main()
