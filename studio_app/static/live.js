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

class HtmlPagesAdapter {
  constructor() {
    this.book = null;
    this.container = null;
    this.iframe = null;
    this.currentPage = 1;
    this.totalPages = 0;
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
      const r = await fetch(
        `/api/books/${this.book.id}/view/page-${n}.html`,
        { method: 'HEAD' },
      );
      if (!r.ok) break;
      n += 1;
    }
    return Math.max(1, n - 1);
  }

  async goToPage(n) {
    const total = this.getTotalPages();
    this.currentPage = Math.min(Math.max(1, n), total || n);
    this.iframe.src =
      `/api/books/${this.book.id}/view/page-${this.currentPage}.html`;
  }

  getTotalPages() {
    return this.totalPages || this.book?.pages || 1;
  }

  getCurrentViewerPage() {
    return this.currentPage;
  }

  async search(query) {
    if (!query || !this.iframe.contentWindow) return;
    try {
      const doc = this.iframe.contentDocument;
      if (!doc || !doc.body) return;
      const text = doc.body.innerText || '';
      if (text.toLowerCase().includes(query.toLowerCase())) {
        doc.body.style.outline = '2px solid #4a9';
        setTimeout(() => { doc.body.style.outline = ''; }, 1500);
      }
    } catch (_) {
      /* cross-origin guard */
    }
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
  }

  async init(container, book) {
    this.container = container;
    this.book = book;
    this.currentPage = Math.max(1, book.current_page || 1);
    container.innerHTML = '';
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'page-frame';
    container.appendChild(this.canvas);
    const url = `/api/books/${book.id}/view/source`;
    this.pdf = await pdfjsLib.getDocument(url).promise;
    await this.goToPage(this.currentPage);
  }

  async goToPage(n) {
    if (!this.pdf) return;
    const total = this.getTotalPages();
    this.currentPage = Math.min(Math.max(1, n), total);
    const page = await this.pdf.getPage(this.currentPage);
    const viewport = page.getViewport({ scale: 1.25 });
    this.canvas.height = viewport.height;
    this.canvas.width = viewport.width;
    if (this._renderTask) {
      this._renderTask.cancel();
    }
    this._renderTask = page.render({
      canvasContext: this.canvas.getContext('2d'),
      viewport,
    });
    await this._renderTask.promise;
  }

  getTotalPages() {
    return this.pdf?.numPages || this.book?.pages || 1;
  }

  getCurrentViewerPage() {
    return this.currentPage;
  }

  async search(query) {
    if (!query || !this.pdf) return;
    const q = query.toLowerCase();
    for (let i = 1; i <= this.getTotalPages(); i += 1) {
      const page = await this.pdf.getPage(i);
      const content = await page.getTextContent();
      const text = content.items.map((it) => it.str).join(' ').toLowerCase();
      if (text.includes(q)) {
        await this.goToPage(i);
        this.canvas.style.outline = '2px solid #4a9';
        setTimeout(() => { this.canvas.style.outline = ''; }, 1500);
        return;
      }
    }
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
      if (typeof idx === 'number') this.currentPage = idx + 1;
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

  async search(query) {
    if (!query || !this.bookObj) return;
    const results = await this.bookObj.search(query);
    if (results?.length) {
      await this.rendition.display(results[0].cfi);
    }
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
    this.dragStart = null;
    this.dragPreview = null;

    this.viewerHost = paneEl.querySelector('.viewer-host');
    this.viewerPageEl = paneEl.querySelector('.viewer-page');
    this.pageCounterEl = paneEl.querySelector('.page-counter');
    this.paceBadgeEl = paneEl.querySelector('.pace-badge');
    this.sessionTimerEl = paneEl.querySelector('.session-timer');
    this.sessionIdEl = paneEl.querySelector('.session-id-label');
    this.statusEl = paneEl.querySelector('.pane-status');
    this.marksRail = paneEl.querySelector('.marks-rail');
    this.searchInput = paneEl.querySelector('.search-input');
    this.titleEl = paneEl.querySelector('.pane-title');

    paneEl.addEventListener('mousedown', () => this.onFocus(this));
    paneEl.querySelector('.page-inc').addEventListener('click', () => this.adjustActivePage(1));
    paneEl.querySelector('.page-dec').addEventListener('click', () => this.adjustActivePage(-1));
    paneEl.querySelector('.pane-close').addEventListener('click', () => this.close());
    this.paceBadgeEl.addEventListener('click', () => this.cyclePaceUnit());
    this.searchInput.addEventListener('input', () => this.renderMarksRail());
    this.viewerHost.addEventListener('mousedown', (e) => this.onMarkDragStart(e));
    this.viewerHost.addEventListener('mousemove', (e) => this.onMarkDragMove(e));
    this.viewerHost.addEventListener('mouseup', (e) => this.onMarkDragEnd(e));
  }

  async init() {
    this.titleEl.textContent = this.book.title;
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
    this.startPage = session.start_page;
    this.trackedProgressPage = session.tracked_progress_page;
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
    const next = Math.min(Math.max(1, this.trackedProgressPage + delta), total);
    if (next === this.trackedProgressPage) return;
    this.trackedProgressPage = next;
    this.updateActivePageUI();
    this.scheduleActivePagePatch();
    this.updatePaceBadge();
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
      : '<li class="muted">No marks</li>';
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
    if (!this.dragStart || !this.dragPreview) return;
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
    if (!this.dragStart || !this.dragPreview) return;
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
    if (e.key === 'm' || e.key === 'M') {
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
  const panesRoot = document.getElementById('panes');
  const template = panesRoot.querySelector('.pane');
  panesRoot.innerHTML = '';

  const books = await Promise.all(
    bookIds.map((id) => jsonFetch(`/api/books/${id}`)),
  );

  liveControllers = [];
  books.forEach((book, i) => {
    const pane = template.cloneNode(true);
    pane.removeAttribute('data-template');
    if (i === 0) pane.classList.add('focused');
    panesRoot.appendChild(pane);
    const controller = new PaneController(
      pane,
      book,
      liveSettings,
      setFocusedPane,
      onPaneClose,
    );
    liveControllers.push(controller);
  });

  focusedController = liveControllers[0] || null;
  await Promise.all(liveControllers.map((c) => c.init()));

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
}
