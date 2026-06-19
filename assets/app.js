import { newsData } from "../data/news.js";
import { deepRows } from "../data/deep-analysis.js";
import { podcastRows } from "../data/podcast-highlights.js";
import { xRows } from "../data/x-posts.js";

const page = document.body.dataset.page || "home";
const app = document.getElementById("app");
const pageState = { visible: 12, xVisible: 40, expanded: {}, archiveOpen: false };

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function externalAttrs(url) {
  return /^https?:\/\//i.test(String(url || "")) ? ' target="_blank" rel="noopener noreferrer"' : "";
}

function openIcon() {
  return '<i class="fas fa-arrow-up open-icon" aria-hidden="true"></i>';
}

// Future headline-image pipeline hooks. Keep these slot ids stable:
// - homepage-featured-techmeme: homepage Techmeme lead story image
// - homepage-featured-wsj: homepage WSJ lead story image
const HEADLINE_IMAGE_SLOTS = {
  "feat-techmeme": "homepage-featured-techmeme",
  "feat-wsj": "homepage-featured-wsj",
};

function titleText(item) {
  return item.title_zh || item.title_en || item.cn || "Untitled";
}

function subtitleText(item) {
  if (item.title_zh && item.title_en && item.title_zh !== item.title_en) return item.title_en;
  return item.summary_zh || item.summary_en || item.en || "";
}

function imageText(item) {
  return item.image_url || item.hero_image_url || item.image || "";
}

function imageCreditText(item) {
  return item.image_credit || "";
}

const HERO_MIN_IMAGE_WIDTH = 420;
const HERO_MIN_IMAGE_HEIGHT = 180;

function hideFeaturedImage(image, className) {
  const media = image.closest(".featured-media");
  if (!media) return;
  media.classList.add(className);
  image.remove();
}

function evaluateFeaturedImage(image) {
  const media = image.closest(".featured-media");
  if (!media) return;

  const width = image.naturalWidth || 0;
  const height = image.naturalHeight || 0;
  if (!width || !height) {
    hideFeaturedImage(image, "image-failed");
    return;
  }

  if (width < HERO_MIN_IMAGE_WIDTH || height < HERO_MIN_IMAGE_HEIGHT) {
    hideFeaturedImage(image, "image-too-small");
    return;
  }

  const mediaRatio = media.clientWidth && media.clientHeight ? media.clientWidth / media.clientHeight : 0;
  const imageRatio = width / height;
  media.classList.add(mediaRatio && imageRatio < mediaRatio * 0.86 ? "image-contain" : "image-cover");
}

function setupFeaturedImages(root = document) {
  root.querySelectorAll(".featured-image").forEach((image) => {
    image.addEventListener("load", () => evaluateFeaturedImage(image), { once: true });
    image.addEventListener("error", () => hideFeaturedImage(image, "image-failed"), { once: true });
    if (image.complete) {
      if (image.naturalWidth) evaluateFeaturedImage(image);
      else hideFeaturedImage(image, "image-failed");
    }
  });
}

function dateText(value) {
  return escapeHtml(String(value || "").replace("T", " ").trim());
}

function renderNav(active) {
  const items = [
    { key: "techmeme", label: "Techmeme", href: page === "home" ? "#techmeme-section" : "index.html#techmeme-section" },
    { key: "wsj", label: "WSJ Tech", href: page === "home" ? "#wsj-section" : "index.html#wsj-section" },
    { key: "analysis", label: "Deep Analysis", href: "deep-analysis.html" },
    { key: "podcast", label: "Podcast", href: "podcast-highlights.html" },
    { key: "x", label: "X Posts", href: "x-posts.html" },
  ];
  return `
    <a class="skip-link" href="#app">Skip to content</a>
    <nav class="site-nav" aria-label="Primary navigation">
      <div class="nav-inner">
        <div class="nav-links">
          ${items.map((item) => {
            const on = item.key === active;
            return `<a class="nav-pill${on ? " is-active" : ""}" href="${item.href}"${on ? ' aria-current="page"' : ""}>${item.label}</a>`;
          }).join("")}
        </div>
        <a class="home-orb" href="index.html" aria-label="回到策展首頁" title="首頁"><i class="fas fa-home" aria-hidden="true"></i></a>
      </div>
    </nav>
  `;
}

function renderMasthead({ active = "techmeme", storyCount = null } = {}) {
  const meta = storyCount ? `${escapeHtml(newsData.date)} | 共 ${storyCount} 則精選` : escapeHtml(newsData.date);
  return `
    ${renderNav(active)}
    <header class="masthead">
      <div aria-hidden="true" style="position:absolute; inset:19px; border:1px solid rgba(206,170,92,.22); pointer-events:none;"></div>
      <div class="masthead-inner">
        <div class="masthead-badge"><span>JD</span></div>
        <div class="masthead-kicker">
          <span class="line"></span><span class="diamond">&#9670;</span><strong>每日科技精選</strong><span class="diamond">&#9670;</span><span class="line"></span>
        </div>
        <h1 class="wordmark">Joyce&rsquo;s <span>Daily</span></h1>
        <div class="fleuron"><span></span><b>&#10086;</b><span></span></div>
        <div class="masthead-meta">${meta}</div>
      </div>
    </header>
  `;
}

function mountMasthead(options) {
  if (document.querySelector(".masthead")) return;
  document.body.insertAdjacentHTML("afterbegin", renderMasthead(options));
}

function sectionHeading({ id, icon, title, date, edit = false, count = "" }) {
  return `
    <div id="${id}" class="section-heading${edit ? " is-edit" : ""}">
      ${icon ? `<i class="fas ${icon}" aria-hidden="true"></i>` : ""}
      <h2>${escapeHtml(title)}</h2>
      ${date ? `<span class="section-date"><i class="far fa-calendar-alt" aria-hidden="true"></i>${escapeHtml(date)}</span>` : ""}
      ${count ? `<span class="feed-count">${escapeHtml(count)}</span>` : ""}
    </div>
  `;
}

function featuredCard(item, slotId) {
  const url = item.url || "#";
  const source = item.source || item.media_source || (slotId === "feat-wsj" ? "Wall Street Journal" : "Source");
  const title = titleText(item);
  const subtitle = subtitleText(item);
  const image = imageText(item);
  const imageCredit = imageCreditText(item);
  const imageSlot = HEADLINE_IMAGE_SLOTS[slotId] || slotId;
  return `
    <article class="featured-card">
      <div class="featured-media${image ? " has-image" : ""}">
        <span class="feature-badge">頭條</span>
        <!-- HEADLINE_IMAGE_SLOT ${imageSlot}: populated from item.image_url when available. -->
        ${image ? `<img class="featured-image" src="${escapeHtml(image)}" alt="${escapeHtml(item.image_alt || title)}" loading="lazy" referrerpolicy="no-referrer">` : ""}
        ${imageCredit ? `<div class="image-credit">${escapeHtml(imageCredit)}</div>` : ""}
        <div class="placeholder-mark" data-slot="${slotId}" data-image-slot="${imageSlot}" data-image-role="homepage-lead-image">
          <div><i class="far fa-image" aria-hidden="true"></i><span>拖入頭條配圖</span><br><small>or browse files</small></div>
        </div>
      </div>
      <div class="featured-copy">
        <div class="source-label">${escapeHtml(source)}</div>
        <a href="${escapeHtml(url)}"${externalAttrs(url)} style="text-decoration:none;">
          <h3 class="featured-title">${escapeHtml(title)}</h3>
        </a>
        ${subtitle ? `<div class="featured-subtitle">${escapeHtml(subtitle)}</div>` : ""}
        <a class="pill pill-news" href="${escapeHtml(url)}"${externalAttrs(url)}>閱讀全文 &rarr;</a>
      </div>
    </article>
  `;
}

function newsRow(item, fallbackSource) {
  const url = item.url || "#";
  const source = item.source || item.media_source || fallbackSource;
  const subtitle = subtitleText(item);
  return `
    <a class="news-row" href="${escapeHtml(url)}"${externalAttrs(url)}>
      <div class="news-title">${escapeHtml(titleText(item))}</div>
      ${subtitle ? `<div class="news-subtitle">${escapeHtml(subtitle)}</div>` : ""}
      <div class="news-source">${escapeHtml(source)} &rarr;</div>
    </a>
  `;
}

function homeTeaser(row, kind) {
  const isPodcast = kind === "podcast";
  const chip = isPodcast ? row.show_name || "Podcast" : row.source || "Deep Analysis";
  const date = isPodcast ? row.date : row.article_date || row.first_seen_date || row.latest_seen_date || "";
  const href = isPodcast ? row.original_link : row.url;
  const hrefLabel = isPodcast ? "Listen" : chip;
  const historyHref = isPodcast ? "podcast-highlights.html" : "deep-analysis.html";
  return `
    <article class="feed-card home-teaser">
      <span class="chip">${escapeHtml(chip)}</span>
      <h3>${escapeHtml(row.title)}</h3>
      <div class="card-date" style="margin-bottom:14px;">${dateText(date)}</div>
      <p class="card-summary">${escapeHtml(row.preview || "")}</p>
      <div style="display:flex; gap:18px; flex-wrap:wrap; align-items:center; margin-top:auto;">
        ${href ? `<a href="${escapeHtml(href)}"${externalAttrs(href)} style="text-decoration:none; font-size:.78rem; font-weight:700; letter-spacing:.4px; text-transform:uppercase; color:var(--edit);">${escapeHtml(hrefLabel)} &rarr;</a>` : ""}
        <a href="${historyHref}" style="text-decoration:none; font-size:.78rem; font-weight:700; letter-spacing:.4px; text-transform:uppercase; color:var(--muted);">Read history &rarr;</a>
      </div>
    </article>
  `;
}

function renderArchives() {
  const rows = newsData.archives || [];
  const visible = pageState.archiveOpen ? rows : rows.slice(0, 7);
  return `
    <section class="archive-section">
      <div class="archive-box">
        <h3><i class="fas fa-folder-open" aria-hidden="true" style="color:var(--news); font-size:1.05rem;"></i>日報存檔</h3>
        <ul class="archive-list${pageState.archiveOpen ? "" : " is-collapsed"}">
          ${visible.map((row) => `
            <li><a href="${escapeHtml(row.href)}"${externalAttrs(row.href)}><i class="far fa-file-lines" aria-hidden="true" style="color:var(--muted); font-size:.85rem;"></i>${escapeHtml(row.label)}</a></li>
          `).join("")}
        </ul>
        ${rows.length > 7 ? `<button class="archive-toggle" type="button" data-archive-toggle>${pageState.archiveOpen ? "收合存檔" : "顯示更多存檔"}</button>` : ""}
      </div>
    </section>
  `;
}

function renderHome() {
  const techmeme = newsData.techmeme || [];
  const wsj = newsData.wsj || [];
  mountMasthead({ active: "techmeme", storyCount: techmeme.length + wsj.length });
  app.className = "home-shell";
  app.innerHTML = `
    ${sectionHeading({ id: "techmeme-section", icon: "fa-bolt", title: "Techmeme Main Feed", date: newsData.date })}
    ${techmeme.length ? featuredCard(techmeme[0], "feat-techmeme") : ""}
    <div class="news-grid">${techmeme.slice(1).map((item) => newsRow(item, "Techmeme")).join("")}</div>
    ${sectionHeading({ id: "wsj-section", icon: "fa-newspaper", title: "WSJ Technology Top 10", date: newsData.date })}
    ${wsj.length ? featuredCard(wsj[0], "feat-wsj") : ""}
    <div class="news-grid">${wsj.slice(1).map((item) => newsRow(item, "WSJ")).join("")}</div>
    ${sectionHeading({ id: "analysis-section", icon: "fa-feather-alt", title: "Deep Analysis", edit: true })}
    <div class="teaser-grid">${(newsData.analysis || []).map((row) => homeTeaser(row, "analysis")).join("")}</div>
    ${sectionHeading({ id: "podcast-section", icon: "fa-microphone-alt", title: "Podcast Highlights", edit: true, count: (newsData.podcast?.[0]?.date || "").slice(0, 10) })}
    <div class="teaser-grid">${(newsData.podcast || []).map((row) => homeTeaser(row, "podcast")).join("")}</div>
  `;
  setupFeaturedImages(app);
  document.body.insertAdjacentHTML("beforeend", renderArchives() + '<footer class="site-footer"><p>由 Doraemon-Mobby 為 Joyce 精心策展</p></footer>');
  setupHomeSpy();
}

function renderArticleCard(row, kind) {
  const isPodcast = kind === "podcast";
  const expanded = !!pageState.expanded[row.id];
  const hasDetails = isPodcast ? Boolean(row.details_html && row.details_html.trim()) : Boolean(row.content_html);
  const chip = isPodcast ? row.show_name || "Podcast" : row.source || "Deep Analysis";
  const date = isPodcast ? row.date : row.article_date || row.first_seen_date || row.latest_seen_date || "";
  const url = isPodcast ? row.original_link : row.url;
  const label = isPodcast ? "Listen" : "Original";
  const summary = isPodcast
    ? `<div class="article-body">${row.summary_html || escapeHtml(row.preview || "")}</div>`
    : `<p class="card-summary">${escapeHtml(row.preview || "")}</p>`;
  const body = isPodcast ? row.details_html : row.content_html;
  return `
    <article class="feed-card">
      <div class="card-meta"><span class="chip">${escapeHtml(chip)}</span><span class="card-date">${dateText(date)}</span></div>
      <h3>${escapeHtml(row.title)}</h3>
      ${summary}
      ${expanded && hasDetails ? `<div class="article-body" style="margin-top:14px; padding-top:14px; border-top:1px dashed var(--line);">${body || ""}</div>` : ""}
      <div class="card-actions">
        ${hasDetails ? `<button class="pill pill-soft" type="button" data-toggle="${escapeHtml(row.id)}">${expanded ? (isPodcast ? "收合內容" : "收合全文") : "展開全文"}</button>` : "<span></span>"}
        ${url ? `<a class="pill" href="${escapeHtml(url)}"${externalAttrs(url)}>${label} &rarr;</a>` : ""}
      </div>
    </article>
  `;
}

function renderFeedPage({ rows, active, title, icon, kind }) {
  mountMasthead({ active });
  app.className = "reading-shell";
  const shown = rows.slice(0, pageState.visible);
  app.innerHTML = `
    ${sectionHeading({ id: "feed-title", icon, title, edit: active !== "x", count: `目前顯示 ${shown.length} / ${rows.length}` })}
    <div class="feed-stack">${shown.map((row) => renderArticleCard(row, kind)).join("")}</div>
    ${pageState.visible < rows.length ? `<div class="load-row"><button class="pill pill-filled" type="button" data-load-more>載入更多</button></div>` : ""}
  `;
}

function xCard(row) {
  return `
    <article class="x-card">
      <div class="x-top">
        <span class="chip chip-neutral">@${escapeHtml(row.handle)}</span>
        ${row.show_google_news_badge ? '<span class="chip chip-neutral" style="color:var(--muted); font-size:.72rem;">Google News 公開節錄</span>' : ""}
        <span class="x-time">${dateText(row.display_time)}</span>
      </div>
      <div class="x-copy x-translation">${escapeHtml(row.translation || row.primary_text)}</div>
      ${row.primary_text ? `<div class="x-copy x-original">${escapeHtml(row.primary_text)}</div>` : ""}
      <div class="x-link-row"><a class="pill x-link" href="${escapeHtml(row.post_url)}"${externalAttrs(row.post_url)}>在 X 開啟 ${openIcon()}</a></div>
    </article>
  `;
}

function renderXPage() {
  mountMasthead({ active: "x" });
  app.className = "reading-shell";
  const shown = xRows.slice(0, pageState.xVisible);
  app.innerHTML = `
    ${sectionHeading({ id: "feed-title", icon: "", title: "X Posts", count: `目前顯示 ${shown.length} / ${xRows.length}` })}
    <div class="feed-stack">${shown.map(xCard).join("")}</div>
    ${pageState.xVisible < xRows.length ? `<div class="load-row"><button class="pill pill-ink" type="button" data-x-load-more>載入更多</button></div>` : ""}
  `;
}

function setupHomeSpy() {
  const links = [...document.querySelectorAll(".nav-pill[href^='#']")];
  const map = new Map(links.map((link) => [link.getAttribute("href").slice(1), link]));
  if (!("IntersectionObserver" in window)) return;
  const observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    links.forEach((link) => link.classList.remove("is-active"));
    const active = map.get(visible.target.id);
    if (active) active.classList.add("is-active");
  }, { rootMargin: "-18% 0px -62% 0px", threshold: [0.1, 0.25, 0.5] });
  map.forEach((_, id) => {
    const section = document.getElementById(id);
    if (section) observer.observe(section);
  });
}

document.addEventListener("click", (event) => {
  const archiveButton = event.target.closest("[data-archive-toggle]");
  if (archiveButton) {
    pageState.archiveOpen = !pageState.archiveOpen;
    document.querySelector(".archive-section").outerHTML = renderArchives();
    return;
  }

  const toggle = event.target.closest("[data-toggle]");
  if (toggle) {
    const id = toggle.dataset.toggle;
    pageState.expanded[id] = !pageState.expanded[id];
    if (page === "deep") renderFeedPage({ rows: deepRows, active: "analysis", title: "Deep Analysis", icon: "fa-feather-alt", kind: "analysis" });
    if (page === "podcast") renderFeedPage({ rows: podcastRows, active: "podcast", title: "Podcast Highlights", icon: "fa-microphone-alt", kind: "podcast" });
    return;
  }

  if (event.target.closest("[data-load-more]")) {
    pageState.visible += 12;
    if (page === "deep") renderFeedPage({ rows: deepRows, active: "analysis", title: "Deep Analysis", icon: "fa-feather-alt", kind: "analysis" });
    if (page === "podcast") renderFeedPage({ rows: podcastRows, active: "podcast", title: "Podcast Highlights", icon: "fa-microphone-alt", kind: "podcast" });
    return;
  }

  if (event.target.closest("[data-x-load-more]")) {
    pageState.xVisible += 30;
    renderXPage();
  }
});

if (page === "home") {
  renderHome();
} else if (page === "deep") {
  renderFeedPage({ rows: deepRows, active: "analysis", title: "Deep Analysis", icon: "fa-feather-alt", kind: "analysis" });
} else if (page === "podcast") {
  renderFeedPage({ rows: podcastRows, active: "podcast", title: "Podcast Highlights", icon: "fa-microphone-alt", kind: "podcast" });
} else if (page === "x") {
  renderXPage();
}
