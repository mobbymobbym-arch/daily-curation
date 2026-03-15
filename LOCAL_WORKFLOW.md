# Local Workflow Execution Guide

This document explains how to use the automated tools located in the `~/daily-curation` folder to generate daily news updates. This workflow is designed to be easily triggered by a daily cron job.

## Prerequisites
- The environment must have Python 3 installed.
- Ensure any required dependencies (like `urllib`, `xml.etree.ElementTree`) are available (most are built-in).
- A valid `gemini` CLI tool must be installed and configured in your path if you intend to run the `generate_deep_analysis.py` script.

## Core Workflow Scripts

### 1. Daily News Generation (`python3 scripts/run_daily_news.py`)

This is the main entry point for generating the standard daily news HTML. 

**Standard Execution (Draft Mode)**
```bash
python3 scripts/run_daily_news.py
```
This will fetch the latest RSS items from Techmeme and WSJ and save them to `daily_news_temp.json`. It will **not** update the HTML file, allowing you time to manually edit the JSON file to add Chinese translations (`title_zh`, `summary_zh`).

**Publish Execution (Final Mode)**
```bash
python3 scripts/run_daily_news.py --publish
```
When run with the `--publish` flag, the script will:
1. Fetch latest headlines if they haven't been fetched yet.
2. Run a quality check to ensure Chinese translations exist in `daily_news_temp.json`.
3. Call `scripts/render_news.py` to generate the HTML into `index.html`.
4. Call `scripts/update_archives.py` to update the archive folder sidebar.
5. (Optional) Run `scripts/publish.py` to push changes to GitHub.

---

### 2. Deep Analysis Generation (`python3 scripts/generate_deep_analysis.py`)

This script polls long-form content sources defined in `deep_analysis_sources.json`, fetches the full text using Jina AI, and uses the Gemini CLI to generate a deep analysis summary.

**Execution**
```bash
python3 scripts/generate_deep_analysis.py
```

Running this will:
1. Check sources against `analysis_state.json` to see if there are new articles.
2. If new articles are found, it fetches the content and sends it to the Gemini CLI.
3. Updates `daily_news_temp.json` with the new deep analysis content.
4. Triggers `scripts/render_news.py` to immediately update the live `index.html` with the new analysis section.

## Automating with Cron
Because you intend to automate this workflow using OpenClaw via cronjob, ensure your cron script navigates to the `~/daily-curation` directory before executing the python scripts to ensure relative paths resolve correctly.

Example cron script snippet:
```bash
#!/bin/bash
cd /Users/lanreset/daily-curation

# 1. Generate Deep Analysis
python3 scripts/generate_deep_analysis.py

# 2. Daily News Fetch (Draft)
python3 scripts/run_daily_news.py

# 3. Translate missing titles/summaries
python3 scripts/translate_news.py

# 4. Publish and Render
python3 scripts/run_daily_news.py --publish
```
