import json
import os
import subprocess
import re
from datetime import datetime

DAILY_NEWS_JSON = 'daily_news_temp.json'

def translate_with_gemini(title_en, summary_en):
    """
    Uses the gemini CLI to translate English title and summary into Traditional Chinese.
    Expects a JSON output from the model.
    """
    prompt = f"""
    You are an expert technology news translator and editor.
    Please translate the following tech news title and summary into fluency Traditional Chinese (zh-TW).
    Keep tech terms in English if they are commonly used that way (e.g., AI, GPU, API).
    Make the tone professional and engaging for a tech-savvy audience in Taiwan.

    TITLE_EN:
    {title_en}

    SUMMARY_EN:
    {summary_en}

    OUTPUT FORMAT:
    Output ONLY a valid JSON object with the following keys. Do not output any markdown formatting or extra text outside the JSON.
    {{
        "title_zh": "翻譯後的繁體中文標題",
        "summary_zh": "翻譯後的繁體中文摘要"
    }}
    """

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
        stdout, stderr = proc.communicate(input=prompt, timeout=180)

        # The CLI itself might return a JSON shell, or the raw model output
        try:
            cli_response = json.loads(stdout)
            # gemini CLI often nests the output in a 'response' key
            ai_output = cli_response.get("response", stdout) 
        except json.JSONDecodeError:
            ai_output = stdout

        # Find the actual JSON structure in the output
        match = re.search(r'\{.*\}', ai_output, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            if "title_zh" in result and "summary_zh" in result:
                return result["title_zh"], result["summary_zh"]
            
        print("   ⚠️ Failed to parse valid translation JSON from output:")
        print(ai_output[:200])
        return None, None

    except subprocess.TimeoutExpired:
        print("   ⚠️ Translation timeout.")
        return None, None
    except Exception as e:
        print(f"   ⚠️ Translation error: {e}")
        return None, None

def process_section(data, section_name):
    """Iterates through a section and translates items missing translations."""
    items = data.get(section_name, [])
    translated_count = 0
    
    for i, item in enumerate(items):
        title_en = item.get("title_en", "")
        summary_en = item.get("summary_en", "")
        
        # Only translate if missing or explicitly null
        if not item.get("title_zh") or not item.get("summary_zh"):
            print(f"   ▶ Translating [{section_name}]: {title_en[:50]}...")
            title_zh, summary_zh = translate_with_gemini(title_en, summary_en)
            
            if title_zh and summary_zh:
                item["title_zh"] = title_zh
                item["summary_zh"] = summary_zh
                translated_count += 1
                print(f"     ✅ Success: {title_zh[:30]}...")
            else:
                print("     ❌ Translation failed for this item.")
    
    return translated_count

def main():
    print("========================================")
    print(f"🈯️ Automated News Translator - {datetime.now()}")
    print("========================================")

    if not os.path.exists(DAILY_NEWS_JSON):
        print(f"❌ '{DAILY_NEWS_JSON}' not found. Please run 'run_daily_news.py' first.")
        return

    with open(DAILY_NEWS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_translated = 0
    
    # Process Techmeme
    print("📰 Checking Techmeme section...")
    total_translated += process_section(data, "techmeme")

    # Process WSJ
    print("\n📰 Checking WSJ section...")
    total_translated += process_section(data, "wsj")

    if total_translated > 0:
        print(f"\n💾 Saving {total_translated} translated items to {DAILY_NEWS_JSON}...")
        with open(DAILY_NEWS_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("✨ Translation complete.")
    else:
        print("\n✨ No items needed translation.")

if __name__ == "__main__":
    main()
