import subprocess
import datetime
import sys
import re
import json
import os
from pathlib import Path

CONFLICT_MARKER_RE = re.compile(r"^(<{7}|={7}|>{7})(?: .*)?$")
SAFE_DAILY_PUBLISH_ENV = "DAILY_CURATION_SAFE_PUBLISH"
SAFE_PUBLISH_KIND_ENV = "DAILY_CURATION_PUBLISH_KIND"

def find_conflict_markers():
    """Scan tracked and untracked files for unresolved Git conflict markers."""
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return [("git-ls-files", 0, result.stderr.strip() or result.stdout.strip())]

    conflicts = []
    for rel_path in result.stdout.splitlines():
        if not rel_path:
            continue
        path = Path(rel_path)
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for lineno, line in enumerate(f, 1):
                    if CONFLICT_MARKER_RE.match(line.rstrip("\n")):
                        conflicts.append((rel_path, lineno, line.strip()))
                        break
        except OSError as e:
            conflicts.append((rel_path, 0, str(e)))
    return conflicts

def abort_if_conflicted():
    conflicts = find_conflict_markers()
    if not conflicts:
        return False

    print("❌ 發現未解決的 Git 衝突標記，已中止發布：")
    for rel_path, lineno, marker in conflicts[:10]:
        if lineno:
            print(f"   - {rel_path}:{lineno} -> {marker}")
        else:
            print(f"   - {rel_path}: {marker}")
    if len(conflicts) > 10:
        print(f"   ... 另有 {len(conflicts) - 10} 個檔案也含有衝突標記")
    print("💡 請先解決衝突後再重新發布。")
    return True

def run_command(command, timeout=None):
    """這是一個小工具，幫我們在終端機裡安全地執行指令，並捕捉任何錯誤"""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"❌ 執行超時 ({timeout}s): {command}")
        return False
    
    # 如果執行失敗（returncode 不是 0 代表有錯誤）
    if result.returncode != 0:
        # 有時候 git commit 失敗只是因為「沒有檔案被修改」，這不算真正的錯誤
        if (
            "nothing to commit" in result.stdout
            or "nothing to commit" in result.stderr
            or "no changes added to commit" in result.stdout
            or "no changes added to commit" in result.stderr
        ):
            print("⚠️ 提示：目前沒有偵測到任何檔案變更，不需要發布。")
            return True # 依然視為流程順利結束
            
        print(f"❌ 執行失敗: {command}")
        print(f"錯誤細節: {result.stderr.strip() or result.stdout.strip()}")
        return False
    return True

def run_command_args(command, timeout=None):
    """Run a command without shell parsing, for exact file path staging."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"❌ 執行超時 ({timeout}s): {' '.join(command)}")
        return False

    if result.returncode != 0:
        print(f"❌ 執行失敗: {' '.join(command)}")
        print(f"錯誤細節: {result.stderr.strip() or result.stdout.strip()}")
        return False
    return True

def has_staged_changes():
    result = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if result.returncode == 0:
        return False
    if result.returncode == 1:
        return True
    print("❌ 無法確認 Git 暫存區狀態，已中止安全發布。")
    return True

def daily_fetch_date():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    news_path = Path("daily_news_temp.json")
    if not news_path.exists():
        return today

    try:
        with news_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return today

    fetch_date = data.get("fetch_date")
    if isinstance(fetch_date, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", fetch_date):
        return fetch_date
    return today

def daily_content_paths():
    fetch_date = daily_fetch_date()
    required_paths = [
        Path("daily_news_temp.json"),
        Path("index.html"),
        Path("deep-analysis.html"),
        Path("podcast-highlights.html"),
        Path("deep_analysis_feed.json"),
        Path("podcast_highlights_feed.json"),
        Path("archives") / f"{fetch_date}.html",
    ]
    optional_paths = [
        Path("analysis_state.json"),
    ]

    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        print("❌ 安全發布找不到必要的日報產物，已中止：")
        for path in missing:
            print(f"   - {path}")
        return []

    paths = [path for path in optional_paths if path.exists()]
    paths.extend(required_paths)
    return [str(path) for path in paths]


def podcast_data_date():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    path = Path("podcast_data.json")
    if not path.exists():
        return today
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return today
    date_value = data.get("date")
    if isinstance(date_value, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", date_value):
        return date_value
    return today


def podcast_content_paths():
    podcast_date = podcast_data_date()
    required_paths = [
        Path("podcast_data.json"),
        Path("index.html"),
        Path("podcast-highlights.html"),
        Path("podcast_highlights_feed.json"),
    ]
    archive_dir = Path("archives")
    optional_paths = sorted(archive_dir.glob("podcast-*.html")) if archive_dir.exists() else []
    current_archive = Path("archives") / f"podcast-{podcast_date}.html"
    if current_archive.exists() and current_archive not in optional_paths:
        optional_paths.append(current_archive)

    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        print("❌ 安全發布找不到必要的 Podcast 產物，已中止：")
        for path in missing:
            print(f"   - {path}")
        return []

    paths = [path for path in optional_paths if path.exists()]
    paths.extend(required_paths)
    return [str(path) for path in paths]


def publish_to_github():
    """自動發布到 GitHub Pages 的核心流程"""
    print("🚀 開始發布更新到網站 (GitHub Pages)...")

    # 0. 先檢查工作目錄內是否殘留 Git 衝突標記
    if abort_if_conflicted():
        return
    
    # 1. 先同步遠端進度 (防呆：避免分支衝突)
    print("🔄 正在同步遠端最新進度...")
    if not run_command("git pull --rebase --autostash origin main"):
        print("❌ 同步遠端失敗，已中止發布，避免將錯誤內容推上線。")
        return

    # 2. 再檢查一次，防止 pull / autostash 後留下衝突標記
    if abort_if_conflicted():
        return
        
    # 3. 將修改過的檔案加入暫存區 (打包)
    print("📦 正在打包變更檔案...")
    if os.environ.get(SAFE_DAILY_PUBLISH_ENV) == "1":
        if has_staged_changes():
            print("❌ 安全發布偵測到已經暫存的其他變更，為避免混入日報發布已中止。")
            print("💡 請先確認那些變更是否也要發布，再重新執行。")
            return

        publish_kind = os.environ.get(SAFE_PUBLISH_KIND_ENV, "daily").strip().lower()
        if publish_kind == "podcast":
            publish_paths = podcast_content_paths()
            publish_label = "Podcast"
        else:
            publish_paths = daily_content_paths()
            publish_label = "日報"
        if not publish_paths:
            return

        print(f"   使用{publish_label}安全發布，只打包以下產物：")
        for path in publish_paths:
            print(f"   - {path}")

        if not run_command_args(["git", "add", "--", *publish_paths]):
            return
    else:
        if not run_command("git add -A"):
            return
        
    # 4. 建立 Commit 訊息 (加上當下時間，讓歷史紀錄清楚明白)
    # 使用台灣時間 (UTC+8) 邏輯或是本地系統時間
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_msg = f"Auto-update: OpenClaw 自動更新 Podcast 摘要 ({current_time})"
    
    print(f"📝 正在寫入發布日誌: {commit_msg}")
    if not run_command(f'git commit -m "{commit_msg}"'):
        return
        
    # 5. 推送到 GitHub (正式上線)
    import time
    print("⏳ 正在推送到 GitHub，這可能需要幾秒鐘...")
    push_success = False
    for attempt in range(3):
        print(f"   ▶ Git Push (Attempt {attempt+1}/3)...")
        if run_command("git push", timeout=60):
            push_success = True
            break
        if attempt < 2:
            print("   ⏳ Retrying in 10 seconds...")
            time.sleep(10)
            
    if not push_success:
        print("❌ 經過 3 次嘗試，Git 推送仍然失敗。請檢查網路狀態或 GitHub 權限。")
        return
        
    print("=======================================================")
    print("🎉 發布大成功！")
    print("網址: https://mobbymobbym-arch.github.io/daily-curation/")
    print("💡 溫馨提醒：GitHub Pages 通常需要 1 到 3 分鐘的時間來刷新快取，")
    print("如果立刻點開沒看到變化，請喝口水、重新整理一下頁面就會出現了！")
    print("=======================================================")

if __name__ == "__main__":
    publish_to_github()
