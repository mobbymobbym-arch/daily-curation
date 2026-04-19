import json
import os
import signal
import subprocess
import re
from datetime import datetime
import time

DAILY_NEWS_JSON = 'daily_news_temp.json'
BATCH_TIMEOUT = 120
MAX_RETRIES = 3
TRANSLATION_BATCH_SIZE = 20

def translate_batch(batch_items, retry_count=0):
    """
    Translates a batch of items using gemini CLI.
    batch_items: list of dicts with 'id', 'title_en', 'summary_en'
    Returns: list of dicts with 'id', 'title_zh', 'summary_zh', or None if failed.
    """
    if not batch_items:
        return []
        
    print(f"   ▶ Attempt {retry_count + 1}/{MAX_RETRIES} for batch of {len(batch_items)} items...")
    
    prompt = f"""
    You are an expert technology news translator and editor.
    Please translate the following tech news titles and summaries into fluent Traditional Chinese (zh-TW).
    Keep tech terms in English if they are commonly used that way (e.g., AI, GPU, API).
    Make the tone professional and engaging for a tech-savvy audience in Taiwan.

    INPUT ITEMS:
    {json.dumps(batch_items, ensure_ascii=False, indent=2)}

    OUTPUT FORMAT:
    Output ONLY a valid JSON array of objects. Do not output any markdown formatting or extra text outside the JSON.
    Each object must have exactly these keys: "id", "title_zh", "summary_zh".
    Ensure the number of output items exactly matches the number of input items.
    [
        {{
            "id": "item_id_here",
            "title_zh": "翻譯後的繁體中文標題",
            "summary_zh": "翻譯後的繁體中文摘要"
        }},
        ...
    ]
    """

    proc = None
    try:
        env = os.environ.copy()
        env['NODE_TLS_REJECT_UNAUTHORIZED'] = '0'
        print(f"   🚀 啟動 Gemini CLI 進程...")
        proc = subprocess.Popen(
            ["gemini", "-p", "Generate JSON only as instructed.", "--model", "gemini-3-flash-preview", "--output-format", "json"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True  # 建立獨立進程組，方便整組 kill
        )
        print(f"   📡 已送出請求 (PID: {proc.pid})，等待回應 (上限 {BATCH_TIMEOUT}s)...")
        stdout, stderr = proc.communicate(input=prompt, timeout=BATCH_TIMEOUT)
        print(f"   📥 收到回應 ({len(stdout)} chars)，開始解析...")
        if proc.returncode not in (0, None):
            print(f"   ⚠️ Gemini CLI exited with code {proc.returncode}.")
        if stderr.strip():
            print(f"   ⚠️ Gemini CLI stderr: {stderr.strip()[:300]}")

        try:
            cli_response = json.loads(stdout)
            ai_output = cli_response.get("response", stdout)
        except json.JSONDecodeError:
            ai_output = stdout

        match = re.search(r'\[.*\]', ai_output, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            if isinstance(result, list) and len(result) == len(batch_items):
                return result
            else:
                print(f"   ⚠️ Result count mismatch or not a list. Expected {len(batch_items)}, got {len(result) if isinstance(result, list) else 'non-list'}.")
        else:
            print(f"   ⚠️ Could not parse JSON array from response: {ai_output[:150]}")

    except subprocess.TimeoutExpired:
        print(f"   ⚠️ Translation timed out after {BATCH_TIMEOUT}s — 正在終止進程組...")
        if proc:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                proc.kill()
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
    except Exception as e:
        print(f"   ⚠️ Translation error: {e}")
        if proc:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                proc.kill()
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
                
    if retry_count < MAX_RETRIES - 1:
        print("   ⏳ Retrying in 5 seconds...")
        time.sleep(5)
        return translate_batch(batch_items, retry_count + 1)
        
    print("   ❌ Exhausted all retries for this batch.")
    return None

def main():
    print("========================================")
    print(f"🈯️ Automated News Translator - {datetime.now()}")
    print(f"   Batch timeout: {BATCH_TIMEOUT}s, Max Retries: {MAX_RETRIES}, Batch size: {TRANSLATION_BATCH_SIZE}")
    print("========================================")

    if not os.path.exists(DAILY_NEWS_JSON):
        print(f"❌ '{DAILY_NEWS_JSON}' not found. Please run 'run_daily_news.py' first.")
        return

    with open(DAILY_NEWS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 1. Gather all items to translate
    batch_requests = []
    item_map = {} # Maps 'section_index' to actual item ref

    for section in ["techmeme", "wsj"]:
        items = data.get(section, [])
        for i, item in enumerate(items):
            title_en = item.get("title_en", "")
            summary_en = item.get("summary_en", "")

            if item.get("title_zh") and not item.get("_translation_skipped"):
                continue

            item_id = f"{section}_{i}"
            batch_requests.append({
                "id": item_id,
                "title_en": title_en,
                "summary_en": summary_en
            })
            item_map[item_id] = item

    if not batch_requests:
        print("✅ No new items require translation.")
        return

    print(f"📰 Found {len(batch_requests)} items to translate. Initiating batch request...")
    
    # 2. Perform Batch Translation
    results = []
    failed_requests = []
    for start in range(0, len(batch_requests), TRANSLATION_BATCH_SIZE):
        batch = batch_requests[start:start + TRANSLATION_BATCH_SIZE]
        print(f"   📦 Translating items {start + 1}-{start + len(batch)} of {len(batch_requests)}...")
        batch_results = translate_batch(batch)
        if batch_results:
            results.extend(batch_results)
        else:
            failed_requests.extend(batch)
    
    # 3. Apply Results
    total_translated = 0
    total_failed = 0

    if results:
        print(f"✅ Successfully translated {len(results)} item(s).")
        for res in results:
            item_id = res.get("id")
            if item_id in item_map:
                item = item_map[item_id]
                item["title_zh"] = res.get("title_zh", "")
                item["summary_zh"] = res.get("summary_zh", "")
                item.pop("_translation_skipped", None)
                total_translated += 1

    if failed_requests:
        print(f"❌ {len(failed_requests)} item(s) failed translation. Falling back to English.")
        for req in failed_requests:
            item_id = req["id"]
            if item_id in item_map:
                item = item_map[item_id]
                item["_translation_skipped"] = True
                item.setdefault("title_zh", item.get("title_en", ""))
                item.setdefault("summary_zh", "")
                total_failed += 1

    # 4. Save to Disk
    with open(DAILY_NEWS_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Translation complete: {total_translated} translated, {total_failed} skipped (fell back to English).")
    if total_failed > 0:
        print("   ℹ️  Items marked '_translation_skipped: true' in the JSON can be re-run later to retry.")

if __name__ == "__main__":
    main()
