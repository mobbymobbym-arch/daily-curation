import re

def clean_vtt(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    text_lines = []
    seen_lines = set()
    
    for line in lines:
        line = line.strip()
        # Skip metadata and timestamps
        if not line:
            continue
        if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
            continue
        if '-->' in line:
            continue
        
        # Remove tags like <c.colorE5E5E5> or <00:00:00.640>
        clean_line = re.sub(r'<[^>]+>', '', line)
        clean_line = clean_line.strip()
        
        if clean_line and clean_line not in seen_lines:
            text_lines.append(clean_line)
            seen_lines.add(clean_line) # Simple dedup for immediate repeats

    # Join and write
    # full_text = ' '.join(text_lines)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for line in text_lines:
            f.write(line + '\n')

if __name__ == '__main__':
    clean_vtt('transcript.en.vtt', 'transcript.txt')
