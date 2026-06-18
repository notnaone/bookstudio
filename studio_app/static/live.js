async function jsonFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

const PACE_UNITS = [
  'chars_per_hour',
  'pages_per_hour',
  'words_per_hour',
  'sec_per_100_pages',
];

const DEFAULT_MARK_COLOR = '#FFFF00';

function createAdapter(format) {
  if (format === 'pdf') return new PdfAdapter();
  if (format === 'epub') return new EpubAdapter();
  if (format === 'txt' || format === 'docx') return new HtmlPagesAdapter();
  throw new Error(`Unsupported format: ${format}`);
}

function pageUrl(bookId, page) {
  const padded = String(page).padStart(4, '0');
  return `/api/books/${bookId}/view/page-${padded}.html`;
}

const SEARCH_HIT_STYLE = 'background-color:#ffe066;color:inherit;padding:0 2px;border-radius:2px';
const SEARCH_ACTIVE_STYLE =
  'background-color:#ff9632;color:inherit;padding:0 2px;border-radius:2px;box-shadow:0 0 0 2px #e86c00';

function countPdfMatchesInItems(items, query) {
  const q = query.toLowerCase();
  const matches = [];
  for (let i = 0; i < items.length; i += 1) {
    const str = items[i].str || '';
    const lower = str.toLowerCase();
    let start = 0;
    let idx = lower.indexOf(q, start);
    while (idx !== -1) {
      matches.push({ itemIndex: i, start: idx, length: q.length, snippet: makeSnippet(str, query) });
      start = idx + q.length;
      idx = lower.indexOf(q, start);
    }
  }
  return matches;
}

function ensureSearchStyles(doc) {
  if (!doc?.head || doc.getElementById('studio-search-style')) return;
  const style = doc.createElement('style');
  style.id = 'studio-search-style';
  style.textContent = `
    mark.search-hit { background: #ffe066; color: inherit; padding: 0 2px; border-radius: 2px; }
    mark.search-hit-active { background: #ff9632; box-shadow: 0 0 0 2px #e86c00; }
  `;
  doc.head.appendChild(style);
}

function clearSearchHighlights(root) {
  if (!root) return;
  root.querySelectorAll('mark.search-hit').forEach((mark) => {
    mark.replaceWith(document.createTextNode(mark.textContent));
  });
  if (root.normalize) root.normalize();
}

function highlightText(root, query) {
  clearSearchHighlights(root);
  if (!query || query.length < 2 || !root) return 0;
  ensureSearchStyles(root.ownerDocument);
  const q = query.toLowerCase();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue?.trim()) return NodeFilter.FILTER_REJECT;
      const tag = node.parentElement?.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'MARK') {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const textNodes = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) textNodes.push(n);
  let hitCount = 0;
  for (const textNode of textNodes) {
    const text = textNode.nodeValue;
    const lower = text.toLowerCase();
    if (!lower.includes(q)) continue;
    const frag = document.createDocumentFragment();
    let pos = 0;
    let idx = lower.indexOf(q, pos);
    while (idx !== -1) {
      if (idx > pos) frag.appendChild(document.createTextNode(text.slice(pos, idx)));
      const mark = document.createElement('mark');
      mark.className = 'search-hit';
      mark.style.cssText = SEARCH_HIT_STYLE;
      mark.textContent = text.slice(idx, idx + query.length);
      frag.appendChild(mark);
      hitCount += 1;
      pos = idx + query.length;
      idx = lower.indexOf(q, pos);
    }
    if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
    textNode.parentNode.replaceChild(frag, textNode);
  }
  return hitCount;
}

function setActiveSearchHit(root, indexOnPage) {
  if (!root) return;
  const hits = root.querySelectorAll('mark.search-hit');
  hits.forEach((el, i) => {
    const active = i === indexOnPage;
    el.classList.toggle('search-hit-active', active);
    el.style.cssText = active ? SEARCH_ACTIVE_STYLE : SEARCH_HIT_STYLE;
  });
  hits[indexOnPage]?.scrollIntoView({ block: 'center', behavior: 'smooth' });
}

function makeSnippet(text, query, radius = 40) {
  const lower = text.toLowerCase();
  const q = query.toLowerCase();
  const idx = lower.indexOf(q);
  if (idx === -1) return text.slice(0, radius * 2).trim();
  const start = Math.max(0, idx - radius);
  const end = Math.min(text.length, idx + query.length + radius);
  return text.slice(start, end).trim();
}

function waitForIframe(iframe) {
  return new Promise((resolve) => {
    if (iframe.contentDocument?.readyState === 'complete') {
      resolve();
      return;
    }
    iframe.addEventListener('load', () => resolve(), { once: true });
  });
}

class HtmlPagesAdapter {
  constructor() {
    this.book = null;
    this.container = null;
    this.iframe = null;
    this.currentPage = 1;
    this.totalPages = 0;
    this.zoomLevel = 1;
    this.lastSearchQuery = '';
    this.activeMatch = null;
  }

  async init(container, book) {
    this.container = container;
    this.book = book;
    this.totalPages = book.pages || await this._probeTotalPages();
    this.currentPage = Math.max(1, book.current_page || 1);
    this.iframe = document.createElement('iframe');
    this.iframe.className = 'page-frame';
    this.iframe.title = book.title;
    container.innerHTML = '';
    container.appendChild(this.iframe);
    await this.goToPage(this.currentPage);
  }

  async _probeTotalPages() {
    let n = 1;
    while (n <= 10000) {
      const r = await fetch(pageUrl(this.book.id, n), { method: 'HEAD' });
      if (!r.ok) break;
      n += 1;
    }
    return Math.max(1, n - 1);
  }

  async goToPage(n) {
    const total = this.getTotalPages();
    this.currentPage = Math.min(Math.max(1, n), total || n);
    this.iframe.src = pageUrl(this.book.id, this.currentPage);
    await waitForIframe(this.iframe);
    this.applyZoom();
    await this.applyPageHighlights();
  }

  async applyPageHighlights() {
    if (!this.lastSearchQuery) return;
    try {
      const doc = this.iframe?.contentDocument;
      if (!doc?.body) return;
      highlightText(doc.body, this.lastSearchQuery);
      if (this.activeMatch && this.activeMatch.page === this.currentPage) {
        setActiveSearchHit(doc.body, this.activeMatch.index_on_page);
      }
    } catch (_) { /* ignore */ }
  }

  setZoom(level) {
    this.zoomLevel = level;
    this.applyZoom();
  }

  applyZoom() {
    if (!this.iframe) return;
    this.iframe.style.transform = `scale(${this.zoomLevel})`;
    this.iframe.style.transformOrigin = 'top center';
    this.iframe.style.width = `${100 / this.zoomLevel}%`;
    this.iframe.style.height = `${100 / this.zoomLevel}%`;
  }

  getTotalPages() {
    return this.totalPages || this.book?.pages || 1;
  }

  getCurrentViewerPage() {
    return this.currentPage;
  }

  async collectMatches(query) {
    return jsonFetch(
      `/api/books/${this.book.id}/search?q=${encodeURIComponent(query)}`,
    );
  }

  async showMatch(query, match) {
    this.lastSearchQuery = query;
    this.activeMatch = match;
    if (this.currentPage !== match.page) {
      await this.goToPage(match.page);
    } else {
      await this.applyPageHighlights();
    }
  }

  clearSearch() {
    this.lastSearchQuery = '';
    this.activeMatch = null;
    try {
      const doc = this.iframe?.contentDocument;
      if (doc?.body) clearSearchHighlights(doc.body);
    } catch (_) { /* ignore */ }
  }
}

class PdfAdapter {
  constructor() {
    this.book = null;
    this.container = null;
    this.pdf = null;
    this.canvas = null;
    this.currentPage = 1;
    this._renderTask = null;
    this.zoomLevel = 1;
    this.baseScale = 1.25;
    this.lastSearchQuery = '';
    this.activeMatch = null;
    this.highlightDiv = null;
    this.textContentItems = [];
    this.currentViewport = null;
  }

  async init(container, book) {
    this.container = container;
    this.book = book;
    this.currentPage = Math.max(1, book.current_page || 1);
    container.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'pdf-page-wrap';
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'page-frame';
    this.highlightDiv = document.createElement('div');
    this.highlightDiv.className = 'pdf-highlight-layer';
    wrap.appendChild(this.canvas);
    wrap.appendChild(this.highlightDiv);
    container.appendChild(wrap);
    const url = `/api/books/${book.id}/view/source`;
    this.pdf = await pdfjsLib.getDocument({
      url,
      standardFontDataUrl: 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/standard_fonts/',
    }).promise;
    await this.goToPage(this.currentPage);
  }

  async goToPage(n) {
    if (!this.pdf) return;
    const total = this.getTotalPages();
    this.currentPage = Math.min(Math.max(1, n), total);
    const page = await this.pdf.getPage(this.currentPage);
    const viewport = page.getViewport({ scale: this.baseScale * this.zoomLevel });
    this.currentViewport = viewport;
    this.canvas.height = viewport.height;
    this.canvas.width = viewport.width;
    this.highlightDiv.style.width = `${viewport.width}px`;
    this.highlightDiv.style.height = `${viewport.height}px`;

    if (this._renderTask) this._renderTask.cancel();
    this._renderTask = page.render({
      canvasContext: this.canvas.getContext('2d'),
      viewport,
    });
    await this._renderTask.promise;

    const textContent = await page.getTextContent();
    this.textContentItems = textContent.items;
    this._drawHighlights();
  }

  _drawHighlights() {
    this.highlightDiv.innerHTML = '';
    if (!this.lastSearchQuery || !this.textContentItems.length || !this.currentViewport) return;
    const q = this.lastSearchQuery.toLowerCase();
    const activeOnPage = this.activeMatch?.page === this.currentPage
      ? this.activeMatch.index_on_page : -1;
    const viewport = this.currentViewport;
    // Flip matrix to convert from PDF Y-up to screen Y-down
    const flipY = [1, 0, 0, -1, 0, 0];
    let hitOnPage = 0;
    let activeEl = null;

    for (const item of this.textContentItems) {
      const str = item.str || '';
      if (!str) continue;
      const lower = str.toLowerCase();
      if (!lower.includes(q)) continue;

      // Compose: viewport.transform × item.transform × flipY
      const composed = pdfjsLib.Util.transform(
        pdfjsLib.Util.transform(viewport.transform, item.transform),
        flipY,
      );
      // composed[4],composed[5] = top-left corner in pixel coords
      // composed[0] = effective horizontal scale, |composed[3]| = effective vertical scale
      const left = composed[4];
      const top = composed[5];
      const scaleRatio = composed[0] / item.transform[0];
      const w = item.width * scaleRatio;
      const h = Math.abs(composed[3]) * (item.height / Math.abs(item.transform[3]));

      if (w <= 0 || h <= 0 || str.length === 0) continue;
      const charW = w / str.length;

      let start = 0;
      let idx = lower.indexOf(q, start);
      while (idx !== -1) {
        const active = hitOnPage === activeOnPage;
        const hlLeft = left + idx * charW;
        const hlW = charW * q.length;

        const span = document.createElement('span');
        span.className = active ? 'search-hit-active' : 'search-hit';
        span.style.left = `${hlLeft}px`;
        span.style.top = `${top}px`;
        span.style.width = `${Math.max(hlW, 2)}px`;
        span.style.height = `${Math.max(h, 4)}px`;
        this.highlightDiv.appendChild(span);
        if (active) activeEl = span;

        hitOnPage += 1;
        start = idx + q.length;
        idx = lower.indexOf(q, start);
      }
    }
    if (activeEl) activeEl.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  async renderTextHighlights() {
    this._drawHighlights();
  }

  getTotalPages() {
    return this.pdf?.numPages || this.book?.pages || 1;
  }

  getCurrentViewerPage() {
    return this.currentPage;
  }

  setZoom(level) {
    this.zoomLevel = level;
    return this.goToPage(this.currentPage);
  }

  async collectMatches(query) {
    if (!this.pdf) return { total: 0, matches: [], truncated: false };
    const matches = [];
    for (let pageNum = 1; pageNum <= this.getTotalPages(); pageNum += 1) {
      const page = await this.pdf.getPage(pageNum);
      const content = await page.getTextContent();
      const pageMatches = countPdfMatchesInItems(content.items, query);
      let indexOnPage = 0;
      for (const match of pageMatches) {
        matches.push({
          page: pageNum,
          index_on_page: indexOnPage,
          global_index: matches.length,
          snippet: match.snippet,
        });
        indexOnPage += 1;
        if (matches.length >= 200) break;
      }
      if (matches.length >= 200) break;
    }
    return { total: matches.length, matches, truncated: matches.length >= 200 };
  }

  async showMatch(query, match) {
    this.lastSearchQuery = query;
    this.activeMatch = match;
    await this.goToPage(match.page);
  }

  clearSearch() {
    this.lastSearchQuery = '';
    this.activeMatch = null;
    if (this.highlightDiv) this.highlightDiv.innerHTML = '';
    this.textContentItems = [];
    if (this.canvas) this.canvas.style.outline = '';
  }
}

class EpubAdapter {
  constructor() {
    this.book = null;
    this.container = null;
    this.rendition = null;
    this.bookObj = null;
    this.currentPage = 1;
    this.spineLength = 0;
    this.zoomLevel = 1;
    this.lastSearchQuery = '';
    this.activeMatch = null;
    this.searchCfis = [];
  }

  async init(container, book) {
    this.container = container;
    this.book = book;
    this.currentPage = Math.max(1, book.current_page || 1);
    container.innerHTML = '';
    const url = `/api/books/${book.id}/view/source`;
    this.bookObj = ePub(url);
    await this.bookObj.ready;
    this.spineLength = this.bookObj.spine?.length || book.pages || 1;
    this.rendition = this.bookObj.renderTo(container, {
      width: '100%',
      height: '100%',
      flow: 'paginated',
    });
    this.rendition.on('relocated', (loc) => {
      const idx = loc?.start?.index;
      if (typeof idx === 'number') {
        this.currentPage = idx + 1;
        if (this.onPageChange) this.onPageChange();
      }
    });
    await this.goToPage(this.currentPage);
  }

  async goToPage(n) {
    if (!this.rendition) return;
    const total = this.getTotalPages();
    const page = Math.min(Math.max(1, n), total);
    this.currentPage = page;
    const spineIndex = page - 1;
    await this.rendition.display(spineIndex);
  }

  getTotalPages() {
    return this.book?.pages || this.spineLength || 1;
  }

  getCurrentViewerPage() {
    return this.currentPage;
  }

  setZoom(level) {
    this.zoomLevel = level;
    if (this.rendition) {
      this.rendition.themes.fontSize(`${Math.round(100 * level)}%`);
    }
  }

  async collectMatches(query) {
    if (!this.bookObj) return { total: 0, matches: [], truncated: false };
    const results = await this.bookObj.search(query);
    this.searchCfis = results || [];
    const matches = this.searchCfis.map((r, i) => ({
      page: (r.spinePos ?? 0) + 1,
      index_on_page: 0,
      global_index: i,
      snippet: r.excerpt || query,
      cfi: r.cfi,
    }));
    return { total: matches.length, matches, truncated: false };
  }

  async showMatch(query, match) {
    this.lastSearchQuery = query;
    this.activeMatch = match;
    if (match.cfi) {
      await this.rendition.display(match.cfi);
    } else {
      await this.goToPage(match.page);
    }
  }

  clearSearch() {
    this.lastSearchQuery = '';
    this.activeMatch = null;
    this.searchCfis = [];
  }
}

function shouldIgnoreHotkey(e) {
  const t = e.target;
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || t.isContentEditable;
}

function formatDuration(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, '0')}`;
}

function formatPaceValue(pagesAdvanced, activeSeconds, unit, book) {
  if (pagesAdvanced <= 0 || activeSeconds < 60) return '—';
  const hours = activeSeconds / 3600;
  const pagesPerHour = pagesAdvanced / hours;
  switch (unit) {
    case 'pages_per_hour':
      return `${Math.round(pagesPerHour).toLocaleString()} p/h`;
    case 'chars_per_hour': {
      const cpp = book.chars_per_page || 0;
      if (cpp <= 0) return '—';
      return `${Math.round(pagesPerHour * cpp).toLocaleString()} c/h`;
    }
    case 'words_per_hour': {
      const cpp = book.chars_per_page || 0;
      if (cpp <= 0) return '—';
      return `${Math.round((pagesPerHour * cpp) / 5).toLocaleString()} w/h`;
    }
    case 'sec_per_100_pages':
      return `${Math.round((100 * activeSeconds) / pagesAdvanced)} s/100p`;
    default:
      return '—';
  }
}

function formatBaseline(stats, unit, book) {
  if (!stats) return '—';
  switch (unit) {
    case 'pages_per_hour':
      return stats.pages_per_hour > 0
        ? `${Math.round(stats.pages_per_hour).toLocaleString()} p/h`
        : '—';
    case 'chars_per_hour':
      return stats.chars_per_hour > 0
        ? `${Math.round(stats.chars_per_hour).toLocaleString()} c/h`
        : '—';
    case 'words_per_hour': {
      const cph = stats.chars_per_hour || 0;
      return cph > 0 ? `${Math.round(cph / 5).toLocaleString()} w/h` : '—';
    }
    case 'sec_per_100_pages': {
      const pph = stats.pages_per_hour || 0;
      return pph > 0 ? `${Math.round(360000 / pph)} s/100p` : '—';
    }
    default:
      return '—';
  }
}

class PaneController {
  constructor(paneEl, book, settings, onFocus, onClose) {
    this.el = paneEl;
    this.book = book;
    this.settings = settings;
    this.onFocus = onFocus;
    this.onClose = onClose;
    this.adapter = createAdapter(book.format);
    this.marks = [];
    this.sessionId = null;
    this.startPage = 1;
    this.trackedProgressPage = 1;
    this.activeSeconds = 0;
    this.pendingActiveDelta = 0;
    this.lastVisibleAt = null;
    this.heartbeatTimer = null;
    this.sessionTimerInterval = null;
    this.sessionStartMs = Date.now();
    this.activePagePatchTimer = null;
    this.contentSearchTimer = null;
    this.dragStart = null;
    this.dragPreview = null;
    this.highlighterMode = false;
    this.zoomLevel = 1;
    this.searchMatches = [];
    this.activeMatchIndex = -1;
    this.searchDropdownOpen = false;
    this.searchTruncated = false;

    this.viewerHost = paneEl.querySelector('.viewer-host');
    this.highlighterToggle = paneEl.querySelector('.highlighter-mode');
    this.viewerPageEl = paneEl.querySelector('.viewer-page');
    this.pageCounterEl = paneEl.querySelector('.page-counter');
    this.paceBadgeEl = paneEl.querySelector('.pace-badge');
    this.sessionTimerEl = paneEl.querySelector('.session-timer');
    this.sessionIdEl = paneEl.querySelector('.session-id-label');
    this.statusEl = paneEl.querySelector('.pane-status');
    this.marksRail = paneEl.querySelector('.marks-rail');
    this.searchInput = paneEl.querySelector('.search-input');
    this.searchCountEl = paneEl.querySelector('.search-toggle-count');
    this.searchPrevBtn = paneEl.querySelector('.search-prev');
    this.searchNextBtn = paneEl.querySelector('.search-next');
    this.searchDropdown = paneEl.querySelector('.search-dropdown');
    this.titleEl = paneEl.querySelector('.pane-title');
    this.zoomLabelEl = paneEl.querySelector('.zoom-label');

    paneEl.addEventListener('mousedown', () => this.onFocus(this));
    paneEl.querySelector('.page-inc').addEventListener('click', () => this.adjustActivePage(1));
    paneEl.querySelector('.page-dec').addEventListener('click', () => this.adjustActivePage(-1));
    paneEl.querySelector('.viewer-inc').addEventListener('click', () => this.adjustViewerPage(1));
    paneEl.querySelector('.viewer-dec').addEventListener('click', () => this.adjustViewerPage(-1));
    paneEl.querySelector('.zoom-inc').addEventListener('click', () => this.adjustZoom(0.1));
    paneEl.querySelector('.zoom-dec').addEventListener('click', () => this.adjustZoom(-0.1));
    paneEl.querySelector('.pane-close').addEventListener('click', () => this.close());
    this.paceBadgeEl.addEventListener('click', () => this.cyclePaceUnit());
    this.searchInput.addEventListener('input', () => this.scheduleContentSearch());
    this.searchInput.addEventListener('keydown', (e) => this.onSearchKeydown(e));
    this.searchPrevBtn.addEventListener('click', () => this.stepSearchMatch(-1));
    this.searchNextBtn.addEventListener('click', () => this.stepSearchMatch(1));
    this.searchCountEl.addEventListener('click', () => this.toggleSearchDropdown());
    this.highlighterToggle.addEventListener('change', () => this.setHighlighterMode(this.highlighterToggle.checked));
    this.viewerHost.addEventListener('mousedown', (e) => this.onViewerMouseDown(e));
    this.viewerHost.addEventListener('mousemove', (e) => this.onMarkDragMove(e));
    this.viewerHost.addEventListener('mouseup', (e) => this.onMarkDragEnd(e));
    this.viewerHost.addEventListener('wheel', (e) => this.onViewerWheel(e), { passive: false });
  }

  setHighlighterMode(on) {
    this.highlighterMode = on;
    this.viewerHost.classList.toggle('highlighter-active', on);
    if (!on && this.dragPreview) {
      this.dragPreview.remove();
      this.dragPreview = null;
      this.dragStart = null;
    }
  }

  onViewerMouseDown(e) {
    if (!this.highlighterMode) return;
    this.onMarkDragStart(e);
  }

  onViewerWheel(e) {
    if (this.highlighterMode || shouldIgnoreHotkey(e)) return;
    if (Math.abs(e.deltaY) < 8) return;
    e.preventDefault();
    this.adjustViewerPage(e.deltaY > 0 ? 1 : -1);
  }

  async init() {
    this.titleEl.textContent = this.book.title;
    this.adapter.onPageChange = () => {
      this.updateViewerPageUI();
      this.renderMarkOverlays();
    };
    await this.adapter.init(this.viewerHost, this.book);
    const { marks } = await jsonFetch(`/api/books/${this.book.id}/marks`);
    this.marks = marks;
    await this.startSession();
    this.updateUI();
    this.renderMarksRail();
    this.renderMarkOverlays();
    this.startHeartbeat();
    this.startVisibilityTracking();
  }

  async startSession() {
    const params = new URLSearchParams(window.location.search);
    const existingId = params.get('session_id');
    let session;
    if (existingId) {
      session = await jsonFetch(`/api/reading_session/${existingId}`);
      if (session.ended_at || session.book_id !== this.book.id) {
        session = await jsonFetch('/api/reading_session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ book_id: this.book.id }),
        });
      }
    } else {
      session = await jsonFetch('/api/reading_session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book_id: this.book.id }),
      });
    }
    this.sessionId = session.id;
    this.startPage = session.start_page ?? 1;
    this.trackedProgressPage =
      session.tracked_progress_page ?? session.start_page ?? this.book.current_page ?? 1;
    this.activeSeconds = session.active_seconds || 0;
    if (this.sessionIdEl) {
      this.sessionIdEl.textContent = `#${this.sessionId}`;
    }
  }

  startVisibilityTracking() {
    this.lastVisibleAt = document.visibilityState !== 'hidden' ? Date.now() : null;
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') {
        this.flushActiveDelta();
        this.lastVisibleAt = null;
      } else {
        this.lastVisibleAt = Date.now();
      }
    });
  }

  flushActiveDelta() {
    if (this.lastVisibleAt == null) return;
    const now = Date.now();
    const delta = Math.floor((now - this.lastVisibleAt) / 1000);
    this.lastVisibleAt = now;
    if (delta > 0) this.pendingActiveDelta += delta;
  }

  startHeartbeat() {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    if (this.sessionTimerInterval) clearInterval(this.sessionTimerInterval);
    this.heartbeatTimer = setInterval(() => this.sendHeartbeat(), 10000);
    this.sessionTimerInterval = setInterval(() => this.updateSessionTimer(), 1000);
  }

  async sendHeartbeat() {
    if (this.sessionId == null) return;
    this.flushActiveDelta();
    const delta = this.pendingActiveDelta;
    try {
      const session = await jsonFetch(
        `/api/reading_session/${this.sessionId}/heartbeat`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tracked_progress_page: this.trackedProgressPage,
            active_seconds_delta: delta,
          }),
        },
      );
      this.pendingActiveDelta -= delta;
      this.activeSeconds = session.active_seconds;
      this.updatePaceBadge();
    } catch (e) {
      if (String(e.message).startsWith('409')) {
        this.showStatus(
          'Session was auto-closed after inactivity.',
          true,
          () => this.continueNewSession(),
        );
        clearInterval(this.heartbeatTimer);
        this.heartbeatTimer = null;
      } else {
        this.showStatus(e.message);
      }
    }
  }

  async continueNewSession() {
    const params = new URLSearchParams(window.location.search);
    params.delete('session_id');
    const qs = params.toString();
    window.history.replaceState(
      null,
      '',
      `${window.location.pathname}${qs ? `?${qs}` : ''}`,
    );
    this.statusEl.textContent = '';
    await this.startSession();
    this.startHeartbeat();
    this.updateUI();
  }

  showStatus(msg, withAction = false, action) {
    this.statusEl.textContent = msg;
    if (withAction && action) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = 'Continue';
      btn.style.marginLeft = '8px';
      btn.addEventListener('click', () => action());
      this.statusEl.appendChild(btn);
    }
  }

  adjustActivePage(delta) {
    const total = this.book.pages || this.adapter.getTotalPages() || 9999;
    const current = Number(this.trackedProgressPage) || 1;
    const next = Math.min(Math.max(1, current + delta), total);
    if (next === current) return;
    this.trackedProgressPage = next;
    this.updateActivePageUI();
    this.scheduleActivePagePatch();
    this.updatePaceBadge();
    this.goToViewerPage(next);
  }

  adjustZoom(delta) {
    const next = Math.min(2.5, Math.max(0.5, Math.round((this.zoomLevel + delta) * 10) / 10));
    if (next === this.zoomLevel) return;
    this.zoomLevel = next;
    if (this.adapter.setZoom) this.adapter.setZoom(next);
    if (this.zoomLabelEl) {
      this.zoomLabelEl.textContent = `${Math.round(next * 100)}%`;
    }
  }

  scheduleContentSearch() {
    clearTimeout(this.contentSearchTimer);
    this.contentSearchTimer = setTimeout(() => this.runContentSearch(), 350);
  }

  async runContentSearch() {
    const q = this.searchInput.value.trim();
    if (q.length < 2) {
      this.clearSearchState();
      return;
    }
    if (!this.adapter.collectMatches) return;
    this.searchCountEl.textContent = '…';
    this.searchCountEl.disabled = true;
    this.searchPrevBtn.disabled = true;
    this.searchNextBtn.disabled = true;
    try {
      const data = await this.adapter.collectMatches(q);
      this.searchMatches = data.matches || [];
      this.searchTruncated = Boolean(data.truncated);
      if (!this.searchMatches.length) {
        this.updateSearchUI(0, 0, null, q);
        if (this.adapter.clearSearch) this.adapter.clearSearch();
        return;
      }
      await this.goToSearchMatch(0);
      this.renderSearchDropdown();
    } catch (e) {
      this.showStatus(e.message);
      this.updateSearchUI(0, 0, null, q);
    }
  }

  clearSearchState() {
    this.searchMatches = [];
    this.activeMatchIndex = -1;
    this.searchTruncated = false;
    this.updateSearchUI(0, 0, null, '');
    this.renderSearchDropdown();
    if (this.adapter.clearSearch) this.adapter.clearSearch();
  }

  updateSearchUI(current, total, match, query) {
    const has = total > 0;
    const totalLabel = has && this.searchTruncated ? `${total}+` : String(total);
    this.searchCountEl.textContent = has
      ? `${current}/${totalLabel}${match ? ` · p.${match.page}` : ''}`
      : (query && query.length >= 2 ? '0 found' : '—');
    this.searchCountEl.disabled = !has;
    this.searchPrevBtn.disabled = !has;
    this.searchNextBtn.disabled = !has;
  }

  async goToSearchMatch(index) {
    if (!this.searchMatches.length) return;
    const total = this.searchMatches.length;
    const wrapped = ((index % total) + total) % total;
    this.activeMatchIndex = wrapped;
    const match = this.searchMatches[wrapped];
    const q = this.searchInput.value.trim();
    await this.adapter.showMatch(q, match);
    this.updateSearchUI(wrapped + 1, total, match, q);
    this.renderSearchDropdown();
  }

  stepSearchMatch(delta) {
    if (!this.searchMatches.length) return;
    this.goToSearchMatch(this.activeMatchIndex + delta);
  }

  toggleSearchDropdown() {
    if (!this.searchMatches.length) return;
    this.searchDropdownOpen = !this.searchDropdownOpen;
    this.searchDropdown.classList.toggle('hidden', !this.searchDropdownOpen);
  }

  renderSearchDropdown() {
    if (!this.searchDropdown) return;
    if (!this.searchMatches.length) {
      this.searchDropdown.innerHTML = '';
      this.searchDropdown.classList.add('hidden');
      this.searchDropdownOpen = false;
      return;
    }
    this.searchDropdown.innerHTML = this.searchMatches.map((m, i) => `
      <button type="button" data-match-index="${i}" class="${i === this.activeMatchIndex ? 'active' : ''}">
        <div class="meta">Match ${i + 1} · page ${m.page}</div>
        <div class="snippet">${escapeHtml(m.snippet || '')}</div>
      </button>`).join('');
    this.searchDropdown.querySelectorAll('[data-match-index]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.goToSearchMatch(Number(btn.dataset.matchIndex));
        this.searchDropdownOpen = true;
        this.searchDropdown.classList.remove('hidden');
      });
    });
    if (!this.searchDropdownOpen) {
      this.searchDropdown.classList.add('hidden');
    }
  }

  onSearchKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      this.stepSearchMatch(e.shiftKey ? -1 : 1);
    }
    if (e.key === 'Escape') {
      this.searchDropdown.classList.add('hidden');
      this.searchDropdownOpen = false;
    }
  }

  async adjustViewerPage(delta) {
    const total = this.adapter.getTotalPages();
    const current = this.adapter.getCurrentViewerPage();
    const next = Math.min(Math.max(1, current + delta), total);
    if (next === current) return;
    await this.goToViewerPage(next);
  }

  scheduleActivePagePatch() {
    clearTimeout(this.activePagePatchTimer);
    this.activePagePatchTimer = setTimeout(() => this.patchActivePage(), 500);
  }

  async patchActivePage() {
    try {
      await jsonFetch(`/api/books/${this.book.id}/active_page`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tracked_progress_page: this.trackedProgressPage }),
      });
    } catch (e) {
      this.showStatus(e.message);
    }
  }

  updateUI() {
    this.updateViewerPageUI();
    this.updateActivePageUI();
    this.updatePaceBadge();
    this.updateSessionTimer();
  }

  updateViewerPageUI() {
    const vp = this.adapter.getCurrentViewerPage();
    const total = this.adapter.getTotalPages();
    this.viewerPageEl.textContent = `View ${vp}/${total}`;
  }

  updateActivePageUI() {
    const total = this.book.pages || this.adapter.getTotalPages() || '?';
    this.pageCounterEl.textContent = `Active ${this.trackedProgressPage}/${total}`;
  }

  updatePaceBadge() {
    const pagesAdvanced = this.trackedProgressPage - this.startPage;
    const unit = this.settings.pace_unit;
    const live = formatPaceValue(pagesAdvanced, this.activeSeconds, unit, this.book);
    const baseline = formatBaseline(this.book.stats, unit, this.book);
    this.paceBadgeEl.textContent =
      live === '—' ? '—' : `${live} · base ${baseline}`;
  }

  updateSessionTimer() {
    this.sessionTimerEl.textContent = formatDuration(this.activeSeconds + this.pendingActiveDelta);
  }

  async cyclePaceUnit() {
    const idx = PACE_UNITS.indexOf(this.settings.pace_unit);
    const next = PACE_UNITS[(idx + 1) % PACE_UNITS.length];
    try {
      const updated = await jsonFetch('/api/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pace_unit: next }),
      });
      this.settings.pace_unit = updated.pace_unit;
      liveControllers.forEach((c) => c.updatePaceBadge());
    } catch (e) {
      this.showStatus(e.message);
    }
  }

  renderMarksRail() {
    const q = this.searchInput.value.trim().toLowerCase();
    const filtered = this.marks.filter((m) => {
      if (!q) return true;
      return (m.comment || '').toLowerCase().includes(q)
        || String(m.page).includes(q);
    });
    this.marksRail.innerHTML = filtered.length
      ? filtered.map((m) => `
        <li data-mark-id="${m.id}" data-page="${m.page}">
          <span class="mark-swatch" style="background:${m.color}"></span>
          p.${m.page} ${escapeHtml(m.comment || '(no comment)')}
        </li>`).join('')
      : '';
    if (!filtered.length) return;
    this.marksRail.querySelectorAll('li[data-page]').forEach((li) => {
      li.addEventListener('click', () => {
        const page = Number(li.dataset.page);
        this.goToViewerPage(page);
        li.classList.add('flash');
        setTimeout(() => li.classList.remove('flash'), 800);
      });
    });
  }

  async goToViewerPage(page) {
    await this.adapter.goToPage(page);
    this.updateViewerPageUI();
    this.renderMarkOverlays();
    if (this.searchMatches.length && this.adapter.applyPageHighlights) {
      await this.adapter.applyPageHighlights();
    }
  }

  renderMarkOverlays() {
    this.viewerHost.querySelectorAll('.mark-overlay').forEach((el) => el.remove());
    const page = this.adapter.getCurrentViewerPage();
    this.marks.filter((m) => m.page === page).forEach((m) => {
      const div = document.createElement('div');
      div.className = 'mark-overlay';
      div.style.left = `${m.x_pct}%`;
      div.style.top = `${m.y_pct}%`;
      div.style.width = `${m.w_pct}%`;
      div.style.height = `${m.h_pct}%`;
      div.style.background = m.color;
      div.title = m.comment || '';
      this.viewerHost.appendChild(div);
    });
  }

  onMarkDragStart(e) {
    if (!this.highlighterMode) return;
    if (e.button !== 0 || e.target.classList.contains('mark-overlay')) return;
    this.onFocus(this);
    const rect = this.viewerHost.getBoundingClientRect();
    this.dragStart = {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };
    this.dragPreview = document.createElement('div');
    this.dragPreview.className = 'mark-drag-preview';
    this.viewerHost.appendChild(this.dragPreview);
    e.preventDefault();
  }

  onMarkDragMove(e) {
    if (!this.highlighterMode || !this.dragStart || !this.dragPreview) return;
    const rect = this.viewerHost.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const left = Math.min(this.dragStart.x, x);
    const top = Math.min(this.dragStart.y, y);
    const w = Math.abs(x - this.dragStart.x);
    const h = Math.abs(y - this.dragStart.y);
    Object.assign(this.dragPreview.style, {
      left: `${left}px`,
      top: `${top}px`,
      width: `${w}px`,
      height: `${h}px`,
    });
  }

  async onMarkDragEnd(e) {
    if (!this.highlighterMode || !this.dragStart || !this.dragPreview) return;
    const rect = this.viewerHost.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const left = Math.min(this.dragStart.x, x);
    const top = Math.min(this.dragStart.y, y);
    const w = Math.abs(x - this.dragStart.x);
    const h = Math.abs(y - this.dragStart.y);
    this.dragPreview.remove();
    this.dragPreview = null;
    this.dragStart = null;
    if (w < 8 || h < 8) return;
    const color = prompt('Mark color (hex):', DEFAULT_MARK_COLOR) || DEFAULT_MARK_COLOR;
    const comment = prompt('Comment:', '') || null;
    await this.createMark({
      x_pct: (left / rect.width) * 100,
      y_pct: (top / rect.height) * 100,
      w_pct: (w / rect.width) * 100,
      h_pct: (h / rect.height) * 100,
      color,
      comment,
    });
  }

  async createMarkAtCenter() {
    await this.createMark({
      x_pct: 40,
      y_pct: 40,
      w_pct: 20,
      h_pct: 10,
      color: DEFAULT_MARK_COLOR,
      comment: null,
    });
  }

  async createMark({ x_pct, y_pct, w_pct, h_pct, color, comment }) {
    try {
      const mark = await jsonFetch('/api/marks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          book_id: this.book.id,
          page: this.adapter.getCurrentViewerPage(),
          x_pct,
          y_pct,
          w_pct,
          h_pct,
          color,
          comment,
        }),
      });
      this.marks.push(mark);
      this.renderMarksRail();
      this.renderMarkOverlays();
    } catch (err) {
      this.showStatus(err.message);
    }
  }

  handleHotkey(e) {
    if (shouldIgnoreHotkey(e)) return false;
    if (e.key === 'h' || e.key === 'H') {
      e.preventDefault();
      this.setHighlighterMode(!this.highlighterMode);
      this.highlighterToggle.checked = this.highlighterMode;
      return true;
    }
    if (!this.highlighterMode && (e.key === 'ArrowRight' || e.key === 'ArrowDown')) {
      e.preventDefault();
      this.adjustViewerPage(1);
      return true;
    }
    if (!this.highlighterMode && (e.key === 'ArrowLeft' || e.key === 'ArrowUp')) {
      e.preventDefault();
      this.adjustViewerPage(-1);
      return true;
    }
    if (e.key === ']' || e.key === 'PageDown') {
      e.preventDefault();
      this.adjustActivePage(1);
      return true;
    }
    if (e.key === '[' || e.key === 'PageUp') {
      e.preventDefault();
      this.adjustActivePage(-1);
      return true;
    }
    if (this.highlighterMode && (e.key === 'm' || e.key === 'M')) {
      e.preventDefault();
      this.createMarkAtCenter();
      return true;
    }
    if ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F')) {
      e.preventDefault();
      this.searchInput.focus();
      this.searchInput.select();
      return true;
    }
    return false;
  }

  async endSession() {
    if (this.sessionId == null) return;
    this.flushActiveDelta();
    const totalActive = this.activeSeconds + this.pendingActiveDelta;
    try {
      await jsonFetch(`/api/reading_session/${this.sessionId}/end`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          end_page: this.trackedProgressPage,
          active_seconds: totalActive,
        }),
      });
    } catch (_) {
      /* best effort */
    }
    this.sessionId = null;
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.sessionTimerInterval) {
      clearInterval(this.sessionTimerInterval);
      this.sessionTimerInterval = null;
    }
  }

  async close() {
    await this.endSession();
    this.onClose(this);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

let liveControllers = [];
let focusedController = null;
let liveSettings = { pace_unit: 'chars_per_hour' };
let paneTemplate = null;
let panesRoot = null;

function syncLiveUrl() {
  const ids = liveControllers.map((c) => c.book.id);
  const path = ids.length ? `/live/${ids.join('/')}` : '/live';
  window.history.replaceState(null, '', path);
}

async function mountBookPane(book, { focus = false } = {}) {
  if (!paneTemplate || !panesRoot) return null;
  if (liveControllers.some((c) => c.book.id === book.id)) return null;

  const pane = paneTemplate.cloneNode(true);
  pane.removeAttribute('data-template');
  pane.classList.toggle('focused', focus);
  panesRoot.appendChild(pane);

  const controller = new PaneController(
    pane,
    book,
    liveSettings,
    setFocusedPane,
    onPaneClose,
  );
  liveControllers.push(controller);
  if (focus || !focusedController) {
    setFocusedPane(controller);
  }
  await controller.init();
  syncLiveUrl();
  return controller;
}

async function initLive() {
  const parts = window.location.pathname.split('/').filter(Boolean);
  const bookIds = parts[0] === 'live'
    ? parts.slice(1).map(Number).filter((n) => !Number.isNaN(n))
    : [];
  if (!bookIds.length) {
    document.getElementById('panes').innerHTML =
      '<p class="muted">No book id in URL. Use /live/&lt;id&gt;.</p>';
    return;
  }

  liveSettings = await jsonFetch('/api/settings');
  panesRoot = document.getElementById('panes');
  paneTemplate = panesRoot.querySelector('.pane');
  panesRoot.innerHTML = '';

  const books = await Promise.all(
    bookIds.map((id) => jsonFetch(`/api/books/${id}`)),
  );

  liveControllers = [];
  for (let i = 0; i < books.length; i += 1) {
    await mountBookPane(books[i], { focus: i === 0 });
  }

  focusedController = liveControllers[0] || null;

  const addDialog = document.getElementById('add-pane-dialog');
  const addSelect = document.getElementById('add-pane-select');
  document.getElementById('add-pane-btn').addEventListener('click', async () => {
    const { books: allBooks } = await jsonFetch('/api/books');
    const openIds = new Set(liveControllers.map((c) => c.book.id));
    const choices = allBooks.filter((b) => !openIds.has(b.id));
    if (!choices.length) {
      alert('All library books are already open.');
      return;
    }
    addSelect.innerHTML = choices
      .map((b) => `<option value="${b.id}">${escapeHtml(b.title)}</option>`)
      .join('');
    addDialog.showModal();
  });
  document.getElementById('add-pane-cancel').addEventListener('click', () => addDialog.close());
  document.getElementById('add-pane-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const bookId = Number(addSelect.value);
    if (!bookId) return;
    addDialog.close();
    const book = await jsonFetch(`/api/books/${bookId}`);
    await mountBookPane(book, { focus: true });
  });

  document.addEventListener('keydown', (e) => {
    if (!focusedController || shouldIgnoreHotkey(e)) return;
    focusedController.handleHotkey(e);
  });

  window.addEventListener('beforeunload', () => {
    liveControllers.forEach((c) => {
      if (c.sessionId == null) return;
      c.flushActiveDelta();
      const totalActive = c.activeSeconds + c.pendingActiveDelta;
      navigator.sendBeacon(
        `/api/reading_session/${c.sessionId}/end`,
        new Blob(
          [JSON.stringify({
            end_page: c.trackedProgressPage,
            active_seconds: totalActive,
          })],
          { type: 'application/json' },
        ),
      );
    });
  });
}

function setFocusedPane(controller) {
  focusedController = controller;
  liveControllers.forEach((c) => {
    c.el.classList.toggle('focused', c === controller);
  });
}

function onPaneClose(controller) {
  controller.el.remove();
  liveControllers = liveControllers.filter((c) => c !== controller);
  if (!liveControllers.length) {
    location.href = '/library';
    return;
  }
  if (focusedController === controller) {
    setFocusedPane(liveControllers[0]);
  }
  syncLiveUrl();
}
