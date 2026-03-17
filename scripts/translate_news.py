import json
import os
import subprocess
import re
from datetime import datetime

DAILY_NEWS_JSON = 'daily_news_temp.json'
# Per-item timeout: 45 seconds is enough for normal calls; if gemini hangs beyond
# this, we kill it and skip to the next item rather than blocking forever.
PER_ITEM_TIMEOUT = 45


def translate_with_gemini(title_en, summary_en):
    """
    Uses the gemini CLI to translate English title and summary into Traditional Chinese.
    Includes a hard kill to handle cases where the subprocess hangs at the network level.
    Returns (title_zh, summary_zh) or (None, None) on any failure.
    """
    prompt = f"""
    You are an expert technology news translator and editor.
    Please translate the following tech news title and summary into fluent Traditional Chinese (zh-TW).
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

    proc = None
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
        stdout, stderr = proc.communicate(input=prompt, timeout=PER_ITEM_TIMEOUT)

        # The CLI itself might return a JSON shell, or the raw model output
        try:
            cli_response = json.loads(stdout)
            ai_output = cli_response.get("response", stdout)
        except json.JSONDecodeError:
            ai_output = stdout

        # Find the actual JSON structure in the output
        match = re.search(r'\{.*\}', ai_output, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            if "title_zh" in result and "summary_zh" in result:
                return result["title_zh"], result["summary_zh"]

        print(f"   ⚠️ Could not parse JSON from response: {ai_output[:150]}")
        return None, None

    except subprocess.TimeoutExpired:
        print(f"   ⚠️ Translation timed out after {PER_ITEM_TIMEOUT}s — killing process and skipping item.")
        if proc:
            proc.kill()
            try:
                proc.communicate(timeout=5)  # Reap the zombie process
            except Exception:
                pass
        return None, None

    except Exception as e:
        print(f"   ⚠️ Translation error: {e}")
        if proc:
            try:
                proc.kill()
                proc.communicate(timeout=5)
            except Exception:
                pass
        return None, None


def process_section(data, section_name):
    """
    Iterates through a section and translates items missing translations.
    Saves the entire JSON to disk after every successful translation so that
    progress is never lost even if the script is interrupted later.
    """
    items = data.get(section_name, [])
    translated_count = 0
    failed_count = 0

    for i, item in enumerate(items):
        title_en = item.get("title_en", "")
        summary_en = item.get("summary_en", "")

        # Skip items that already have a Chinese title (idempotent re-runs)
        if item.get("title_zh") and not item.get("_translation_skipped"):
            continue

        print(f"   ▶ [{i+1}/{len(items)}] Translating [{section_name}]: {title_en[:60]}...")
        title_zh, summary_zh = translate_with_gemini(title_en, summary_en)

        if title_zh and summary_zh:
            item["title_zh"] = title_zh
            item["summary_zh"] = summary_zh
            # Clear any previous skip marker
            item.pop("_translation_skipped", None)
            translated_count += 1
            print(f"     ✅ {title_zh[:40]}...")

            # ⚡ Incremental save: write progress to disk immediately
            with open(DAILY_NEWS_JSON, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        else:
            # Mark as skipped so we can identify and retry later
            item["_translation_skipped"] = True
            item.setdefault("title_zh", title_en)   # Fallback to English so rendering doesn't break
            item.setdefault("summary_zh", "")
            failed_count += 1
            print(f"     ⏭️  Skipped (will use English title as fallback).")

    return translated_count, failed_count


def main():
    print("========================================")
    print(f"🈯️ Automated News Translator - {datetime.now()}")
    print(f"   Per-item timeout: {PER_ITEM_TIMEOUT}s")
    print("========================================")

    if not os.path.exists(DAILY_NEWS_JSON):
        print(f"❌ '{DAILY_NEWS_JSON}' not found. Please run 'run_daily_news.py' first.")
        return

    with open(DAILY_NEWS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_translated = 0
    total_failed = 0

    # Process Techmeme
    print("📰 Checking Techmeme section...")
    t, f = process_section(data, "techmeme")
    total_translated += t
    total_failed += f

    # Process WSJ
    print("\n📰 Checking WSJ section...")
    t, f = process_section(data, "wsj")
    total_translated += t
    total_failed += f

    # Final summary
    print(f"\n✅ Translation complete: {total_translated} translated, {total_failed} skipped (fell back to English).")

    if total_failed > 0:
        print("   ℹ️  Items marked '_translation_skipped: true' in the JSON can be re-run later to retry.")

if __name__ == "__main__":
    main()
