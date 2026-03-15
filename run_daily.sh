#!/bin/bash
# ============================================
# 🤖 Daily Curation 自動化主腳本
# 由 crontab 觸發，每天定時執行
# ============================================

set -e

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

# --- 步驟 1: 抓取新聞 ---
echo ""
echo "📰 步驟 1/4: 抓取新聞 (Techmeme + WSJ)"
python3 scripts/run_daily_news.py
echo "   ✅ 新聞抓取完成"

# --- 步驟 2: 翻譯新聞 ---
echo ""
echo "🈯️ 步驟 2/4: 翻譯新聞"
python3 scripts/translate_news.py
echo "   ✅ 翻譯完成"

# --- 步驟 3: 深度分析 ---
echo ""
echo "🧠 步驟 3/4: 深度分析 (7個 RSS 來源)"
python3 scripts/generate_deep_analysis.py
echo "   ✅ 深度分析完成"

# --- 步驟 4: 發布 ---
echo ""
echo "🚀 步驟 4/4: 渲染 + 發布"
python3 scripts/run_daily_news.py --publish
echo "   ✅ 發布完成"

# --- 清理舊 log (保留 30 天) ---
find "$LOG_DIR" -name "daily_*.log" -mtime +30 -delete 2>/dev/null || true

echo ""
echo "========================================"
echo "✨ Daily Curation 完成: $(date)"
echo "========================================"
