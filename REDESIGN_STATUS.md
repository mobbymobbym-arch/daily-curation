# Daily Curation 改版狀態記錄

更新日期：2026-05-06

這份文件用來記錄這次 Daily Curation 改版中，已經和使用者確認的部分，以及正式 publish 前還需要收尾或決定的事項。後續不要只依賴聊天記憶，應該以這份文件作為目前改版狀態的基準。

## 已確認的部分

### Deep Analysis 與 Podcast Highlights 變成獨立分頁

目前已確認新增並使用這兩個獨立分頁：

- `deep-analysis.html`
- `podcast-highlights.html`

這兩個頁面的定位和 `x-posts.html` 類似：它們不是只顯示當日內容，而是保留歷史內容，並且透過預先載入數量與 Read more / load more 的方式慢慢展開舊內容。

目前確認的頁面形式如下：

- Deep Analysis 會從既有 daily archive HTML 和目前的 `index.html` 重新整理出歷史 feed。
- Podcast Highlights 會從 podcast archive HTML、目前的 `podcast_data.json`，以及既有的 `podcast_highlights_feed.json` 整理出歷史 feed。這樣只重建 podcast 分頁時，不會因為 `podcast_data.json` 跨日重置而把舊卡片洗掉。
- Deep Analysis 和 Podcast Highlights 都是單欄形式。
- 兩個頁面卡片上方原本重複的說明文字已移除，因為頁面上方 header 已經說明了頁面定位。

這次檢查時的內容數量：

- Deep Analysis：126 篇。
- Podcast Highlights：19 篇，其中包含本機測試用的 YouTube 單集 `https://www.youtube.com/watch?v=EN7frwQIbKc`。

### Podcast 卡片左上角標籤

Podcast 卡片現在已經有一個專門給左上角 chip 使用的欄位。

新生成的 podcast 卡片會在 `scripts/generate_podcast.py` 裡寫入：

- `show_name`

如果來源是 YouTube，這個欄位會優先使用 `yt-dlp` 抓到的 uploader / channel。這次測試卡片抓到並顯示的是 `Y Combinator`。

舊 podcast 卡片因為以前沒有儲存這個欄位，所以目前由 `scripts/build_section_pages.py` 從標題、摘要、來源網址、以及已知節目名稱規則裡推論。只有真的找不到線索時，才會退回 `YouTube`、`Spotify`、`Apple Podcasts` 或最後的 `Podcast`。

### 生成與發布流程

Daily News 的 publish 流程現在會在發布前重建兩個 section page：

- `scripts/run_daily_news.py` 在 `--publish` 流程中會呼叫 `scripts/build_section_pages.py`。

Podcast 生成流程現在同時支援本機測試和未來正式發布：

- 只測試新版 Podcast Highlights 分頁：`python3 scripts/generate_podcast.py <url> --podcast-highlights-only`
- 本機完整渲染但不 publish：`python3 scripts/generate_podcast.py <url> --no-publish`
- 預設 podcast 生成流程仍然朝向 publish，但已經改成使用 podcast 專用的 safe publish 設定。

`scripts/publish.py` 現在有分開的安全發布路徑：

- Daily content publish。
- Podcast content publish。

### 主頁導航與頁尾目錄

首頁 nav 已經改成連到獨立分頁：

- Deep Analysis -> `/daily-curation/deep-analysis.html`
- Podcast -> `/daily-curation/podcast-highlights.html`
- X Posts -> `/daily-curation/x-posts.html`

原本頁尾目錄不再保留很長的 podcast archive 清單，也不再放「專題分頁」目錄。現在頁尾的結構是：

- 日報存檔清單。
- 日報存檔預設只顯示近 7 筆，其餘較舊日期以「顯示更多存檔」收合。

## 目前首頁會變成什麼形式

目前這個分支的首頁仍然是 daily front page，也就是當日策展首頁。它會保留：

- Techmeme Top 10。
- WSJ Technology Top 10。
- 當日 / 最新 Deep Analysis teaser 卡片。
- 當日 / 最新 Podcast Highlights teaser 卡片。

和舊版不同的是，Deep Analysis 與 Podcast Highlights 在首頁上的定位會變成「今日或最新精選」，而完整歷史內容則交給獨立分頁。

換句話說，目前的主頁設計邏輯是：

- 首頁 = 今天的策展 issue + 最新重點內容。
- `deep-analysis.html` / `podcast-highlights.html` / `x-posts.html` = 各自完整歷史瀑布流。
- 頁尾 = 日報存檔，預設只露出近 7 筆，其餘收合，不再放專題分頁入口。

目前分支實作的是「首頁只放較乾淨的 teaser 卡片，完整 Deep Analysis / Podcast 內容到獨立分頁閱讀」這個版本。首頁不再直接放完整 Deep Analysis 長文或 Podcast 章節全文。
Deep Analysis / Podcast Highlights 區塊右側的 `View all` 已改成較大的 pill 標籤形式，讓它看起來更像分頁入口。

## 正式發布前還沒完成或還需要決定的地方

### 首頁內容深度

已確認採用 teaser 形式。首頁會保留 Deep Analysis 與 Podcast Highlights 的入口和最新摘要，但不在首頁展開完整正文；完整歷史內容和展開閱讀都交給兩個獨立分頁。

### 本機測試 Podcast 卡片

測試單集 `https://www.youtube.com/watch?v=EN7frwQIbKc` 已經在本機生成，並存在於：

- `podcast_data.json`
- `podcast_highlights_feed.json`
- `podcast-highlights.html`

已確認這張 Y Combinator podcast 卡片保留成正式內容，不再視為一次性測試資料。

### 視覺檢查

目前已經確認 HTML / JSON 可生成與解析，也已經做過一輪本機瀏覽器視覺檢查。這次檢查中，首頁手機版 nav、首頁 teaser 形式、Deep Analysis / Podcast Highlights 單欄頁面都已經可以正常顯示。

檢查過程中曾發現 Podcast Highlights 獨立頁的 hero 標題在非常窄的手機視窗下會被切到右側，已經把 section page 的手機版 hero 字級改成固定、較保守的尺寸，避免長標題溢出。

互動功能目前確認的狀態：

- 手機版 nav 是否換行正常。
- 單欄卡片間距是否舒服。
- Load more 的資料邏輯正常，Deep Analysis 由 12 張載入到 24 張，Podcast Highlights 由 10 張載入到 19 張。
- Deep Analysis / Podcast 卡片內的展開與收合使用同一個 toggle handler，已確認展開會加入 `expanded` class 並切換成「收合全文」，收合會移除 `expanded` class 並回到「展開全文」。

### Production publish

這次改版分支目前尚未正式 publish，也還沒有 commit。

正式發布前建議最後確認：

- 跑最後一次 build / verification。
- 再 commit 並 publish 到 GitHub Pages。
