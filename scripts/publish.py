import subprocess
import datetime
import sys
import re
from pathlib import Path

CONFLICT_MARKER_RE = re.compile(r"^(<{7}|={7}|>{7})(?: .*)?$")

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
        if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
            print("⚠️ 提示：目前沒有偵測到任何檔案變更，不需要發布。")
            return True # 依然視為流程順利結束
            
        print(f"❌ 執行失敗: {command}")
        print(f"錯誤細節: {result.stderr.strip() or result.stdout.strip()}")
        return False
    return True

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
        
    # 3. 將所有修改過的檔案加入暫存區 (打包)
    print("📦 正在打包變更檔案...")
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
