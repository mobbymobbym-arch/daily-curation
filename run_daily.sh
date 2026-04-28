#!/bin/bash
# ============================================
# 🤖 Daily Curation 自動化主腳本
# 由 crontab 觸發，每天定時執行
# ============================================

# 注意：不使用 set -e，改用各步驟獨立錯誤捕捉
# 這樣翻譯失敗也能繼續發布，不會整個流程中斷

# 工作目錄
WORK_DIR="$HOME/daily-curation"
LOG_DIR="$WORK_DIR/logs"
LOG_FILE="$LOG_DIR/daily_$(date +%Y-%m-%d).log"

# 環境變數
export PATH="/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/bin:/usr/local/opt/coreutils/libexec/gnubin:/opt/local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export NODE_TLS_REJECT_UNAUTHORIZED=0
export PYTHONUNBUFFERED=1
export DAILY_CURATION_SAFE_PUBLISH=1

# 確認 timeout 指令可用（macOS 需透過 coreutils 的 gtimeout）
TIMEOUT_CMD=""
if command -v timeout &>/dev/null; then
    TIMEOUT_CMD="timeout"
elif command -v gtimeout &>/dev/null; then
    TIMEOUT_CMD="gtimeout"
fi

if [ -z "$TIMEOUT_CMD" ]; then
    echo "⚠️ 警告：找不到 timeout/gtimeout 指令，步驟將不設上限時間"
fi

# 確保 log 目錄存在
mkdir -p "$LOG_DIR"

# 開始記錄
exec >> >(tee -a "$LOG_FILE") 2>&1
echo "========================================"
echo "⏰ Daily Curation 開始: $(date)"
echo "========================================"

cd "$WORK_DIR"

# 追蹤是否有步驟失敗
PIPELINE_OK=true
FAILED_STEPS=""

# Helper: 帶超時執行指令
run_with_timeout() {
    local timeout_secs=$1
    shift
    if [ -n "$TIMEOUT_CMD" ]; then
        $TIMEOUT_CMD --kill-after=10 "$timeout_secs" "$@"
    else
        "$@"
    fi
}

# Helper: 檢查工作目錄內是否殘留 Git 衝突標記
find_conflict_markers() {
    local rel_path
    local found=1

    while IFS= read -r rel_path; do
        [ -z "$rel_path" ] && continue
        if grep -n -m1 -E '^(<<<<<<<|=======|>>>>>>>)( .*)?$' "$rel_path" >/dev/null 2>&1; then
            found=0
            break
        fi
    done < <(git ls-files -co --exclude-standard)

    return $found
}

# Helper: 啟動排程前先同步最新 repo，避免用過時程式碼生產內容
sync_repo_before_run() {
    echo ""
    echo "🔄 啟動前同步最新 repo..."

    if find_conflict_markers; then
        echo "   ❌ 偵測到未解決的 Git 衝突標記，停止今日排程"
        return 1
    fi

    if git pull --rebase --autostash origin main; then
        echo "   ✅ 已同步到最新 repo"
    else
        echo "   ❌ git pull --rebase --autostash 失敗，停止今日排程"
        return 1
    fi

    if find_conflict_markers; then
        echo "   ❌ 同步後仍偵測到 Git 衝突標記，停止今日排程"
        return 1
    fi

    return 0
}

# --- 啟動前：同步 repo ---
if ! sync_repo_before_run; then
    python3 scripts/notify_telegram.py --status "❌ 啟動前同步 repo 失敗或偵測到 Git 衝突，已中斷今日流程"
    exit 1
fi

# --- 步驟 1: 抓取新聞 ---
echo ""
echo "📰 步驟 1/5: 抓取新聞 (Techmeme + WSJ)"
if run_with_timeout 60 python3 scripts/run_daily_news.py; then
    echo "   ✅ 新聞抓取完成"
else
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 124 ]; then
        echo "   ❌ 新聞抓取超時 (60s) — 停止工作流程"
    else
        echo "   ❌ 新聞抓取失敗 (exit code: $EXIT_CODE) — 停止工作流程"
    fi
    python3 scripts/notify_telegram.py --status "❌ 步驟 1 失敗：新聞抓取錯誤，已中斷"
    exit 1
fi

# --- 步驟 2: 深度分析 (提前執行，不依賴翻譯) ---
echo ""
echo "🧠 步驟 2/5: 深度分析 (7個 RSS 來源)"
if run_with_timeout 600 python3 scripts/generate_deep_analysis.py; then
    echo "   ✅ 深度分析完成"
else
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 124 ]; then
        echo "   ⚠️ 深度分析超時 (600s) — 繼續後續步驟"
    else
        echo "   ⚠️ 深度分析有部分失敗 — 繼續後續步驟"
    fi
    PIPELINE_OK=false
    FAILED_STEPS="${FAILED_STEPS}深度分析 "
fi

# --- 步驟 3: 翻譯新聞 ---
echo ""
echo "🈯️ 步驟 3/5: 翻譯新聞"
if run_with_timeout 180 python3 scripts/translate_news.py; then
    echo "   ✅ 翻譯完成"
else
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 124 ]; then
        echo "   ⚠️ 翻譯超時 (180s) — 繼續後續步驟（將以英文作為備援）"
    else
        echo "   ⚠️ 翻譯步驟有部分失敗 — 繼續後續步驟（將以英文作為備援）"
    fi
    PIPELINE_OK=false
    FAILED_STEPS="${FAILED_STEPS}翻譯 "
fi

# --- 步驟 4: 發布 ---
echo ""
echo "🚀 步驟 4/5: 渲染 + 發布"
if run_with_timeout 120 python3 scripts/run_daily_news.py --publish; then
    echo "   ✅ 發布完成"
else
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 124 ]; then
        echo "   ❌ 發布超時 (120s)"
    else
        echo "   ❌ 發布失敗"
    fi
    PIPELINE_OK=false
    FAILED_STEPS="${FAILED_STEPS}發布 "
fi

# --- 步驟 5: Telegram 通知 ---
echo ""
echo "📱 步驟 5/5: 發送 Telegram 通知"
if [ "$PIPELINE_OK" = true ]; then
    run_with_timeout 30 python3 scripts/notify_telegram.py
    echo "   ✅ 通知完成"
else
    echo "   ⚠️ 管線部分步驟失敗，發送告警通知..."
    run_with_timeout 30 python3 scripts/notify_telegram.py --status "⚠️ 今日日報部分步驟失敗：${FAILED_STEPS}— 請檢查 Log"
    echo "   ✅ 告警通知已發送"
fi

# --- 清理舊 log (保留 30 天) ---
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null || true

echo ""
echo "========================================"
if [ "$PIPELINE_OK" = true ]; then
    echo "✨ Daily Curation 全部完成: $(date)"
else
    echo "⚠️ Daily Curation 完成（部分步驟有警告: ${FAILED_STEPS}）: $(date)"
fi
echo "========================================"
