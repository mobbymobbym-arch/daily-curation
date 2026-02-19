import re

def clean_vtt(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove WEBVTT header and Kind/Language
    content = re.sub(r'WEBVTT\nKind:.*\nLanguage:.*\n', '', content)
    
    # Remove timestamps and styles (align:start position:0%)
    content = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*\n', '', content)
    
    # Remove inline timestamps like <00:00:00.539>
    content = re.sub(r'<\d{2}:\d{2}:\d{2}\.\d{3}>', '', content)
    
    # Remove tags like <c>, </c>
    content = re.sub(r'</?c>', '', content)
    
    # Split into lines, strip, and remove empty lines
    lines = content.split('\n')
    cleaned_lines = []
    seen = set()
    for line in lines:
        line = line.strip()
        if line and line not in seen:
            cleaned_lines.append(line)
            # Simple deduplication for adjacent repeated lines often found in VTT
            if len(seen) > 50: # Keep memory small
                seen.clear()
            seen.add(line)
            
    return " ".join(cleaned_lines)

if __name__ == "__main__":
    cleaned_text = clean_vtt('transcript.en.vtt')
    with open('transcript_cleaned.txt', 'w', encoding='utf-8') as f:
        f.write(cleaned_text)
