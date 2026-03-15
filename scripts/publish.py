import subprocess
import datetime
import sys

def run_command(command):
    """這是一個小工具，幫我們在終端機裡安全地執行指令，並捕捉任何錯誤"""
    # 執行指令並擷取輸出結果
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    
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
    
    # 1. 將所有修改過的檔案加入暫存區 (打包)
    print("📦 正在打包變更檔案...")
    if not run_command("git add index.html podcast_data.json"):
        return
        
    # 2. 建立 Commit 訊息 (加上當下時間，讓歷史紀錄清楚明白)
    # 使用台灣時間 (UTC+8) 邏輯或是本地系統時間
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_msg = f"Auto-update: OpenClaw 自動更新 Podcast 摘要 ({current_time})"
    
    print(f"📝 正在寫入發布日誌: {commit_msg}")
    if not run_command(f'git commit -m "{commit_msg}"'):
        return
        
    # 3. 推送到 GitHub (正式上線)
    print("⏳ 正在推送到 GitHub，這可能需要幾秒鐘...")
    if not run_command("git push"):
        return
        
    print("=======================================================")
    print("🎉 發布大成功！")
    print("網址: https://mobbymobbym-arch.github.io/daily-curation/")
    print("💡 溫馨提醒：GitHub Pages 通常需要 1 到 3 分鐘的時間來刷新快取，")
    print("如果立刻點開沒看到變化，請喝口水、重新整理一下頁面就會出現了！")
    print("=======================================================")

if __name__ == "__main__":
    publish_to_github()
