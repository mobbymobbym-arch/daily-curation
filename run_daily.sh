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
export PATH="/opt/local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export NODE_TLS_REJECT_UNAUTHORIZED=0

# 確保 log 目錄存在
mkdir -p "$LOG_DIR"

# 開始記錄
exec > >(tee -a "$LOG_FILE") 2>&1
echo "========================================"
echo "⏰ Daily Curation 開始: $(date)"
echo "========================================"

cd "$WORK_DIR"

# 追蹤是否有步驟失敗
PIPELINE_OK=true

# --- 步驟 1: 抓取新聞 ---
echo ""
echo "📰 步驟 1/5: 抓取新聞 (Techmeme + WSJ)"
if python3 scripts/run_daily_news.py; then
    echo "   ✅ 新聞抓取完成"
else
    echo "   ❌ 新聞抓取失敗 — 停止工作流程"
    python3 scripts/notify_telegram.py --status "❌ 步驟 1 失敗：新聞抓取錯誤，已中斷"
    exit 1
fi

# --- 步驟 2: 翻譯新聞 ---
echo ""
echo "🈯️ 步驟 2/5: 翻譯新聞"
if python3 scripts/translate_news.py; then
    echo "   ✅ 翻譯完成"
else
    echo "   ⚠️ 翻譯步驟有部分失敗 — 繼續後續步驟（將以英文作為備援）"
    PIPELINE_OK=false
fi

# --- 步驟 3: 深度分析 ---
echo ""
echo "🧠 步驟 3/5: 深度分析 (7個 RSS 來源)"
if python3 scripts/generate_deep_analysis.py; then
    echo "   ✅ 深度分析完成"
else
    echo "   ⚠️ 深度分析有部分失敗 — 繼續後續步驟"
    PIPELINE_OK=false
fi

# --- 步驟 4: 發布 ---
echo ""
echo "🚀 步驟 4/5: 渲染 + 發布"
if python3 scripts/run_daily_news.py --publish; then
    echo "   ✅ 發布完成"
else
    echo "   ❌ 發布失敗"
    PIPELINE_OK=false
fi

# --- 步驟 5: Telegram 通知 ---
echo ""
echo "📱 步驟 5/5: 發送 Telegram 通知"
python3 scripts/notify_telegram.py
echo "   ✅ 通知完成"

# --- 清理舊 log (保留 30 天) ---
find "$LOG_DIR" -name "daily_*.log" -mtime +30 -delete 2>/dev/null || true

echo ""
echo "========================================"
if [ "$PIPELINE_OK" = true ]; then
    echo "✨ Daily Curation 全部完成: $(date)"
else
    echo "⚠️ Daily Curation 完成（部分步驟有警告）: $(date)"
fi
echo "========================================"
