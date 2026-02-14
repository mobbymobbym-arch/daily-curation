import os
import re
from datetime import datetime

def update_archives():
    # Read current index.html
    with open('index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract date from header using regex
    # Header format: <header> ... <p>Friday, February 13, 2026</p> ... </header>
    date_match = re.search(r'<header>.*?<p>(.*?)</p>', content, re.DOTALL)
    if date_match:
        date_str = date_match.group(1).strip()
        try:
            dt = datetime.strptime(date_str, "%A, %B %d, %Y")
            file_date = dt.strftime("%Y-%m-%d")
        except:
            file_date = datetime.now().strftime("%Y-%m-%d")
    else:
        file_date = datetime.now().strftime("%Y-%m-%d")

    # Archive path
    archive_dir = 'archive'
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
    
    archive_file = os.path.join(archive_dir, f"{file_date}.html")
    
    # Save the current index to archive
    with open(archive_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Update index.html sidebar with new link
    # Find the "日報存檔" section
    sidebar_marker = '<h3><i class="fas fa-archive"></i> 日報存檔</h3>'
    if sidebar_marker in content:
        parts = content.split(sidebar_marker)
        # parts[1] starts with the ul
        # Find the first </li>
        li_marker = '</li>'
        li_parts = parts[1].split(li_marker, 1)
        
        new_link = f'\n                <li class="archive-item">\n                    <a href="/daily-curation/archive/{file_date}.html" class="archive-link">\n                        <i class="far fa-calendar"></i> {file_date}\n                    </a>\n                </li>'
        
        content = parts[0] + sidebar_marker + li_parts[0] + li_marker + new_link + li_parts[1]

    # Save updated index.html
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Archived current page to {file_date}.html and updated index.html sidebar.")

if __name__ == "__main__":
    update_archives()
