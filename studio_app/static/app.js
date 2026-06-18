async function jsonFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  if (r.status === 204) return null;
  return r.json();
}

async function pickFolder() {
  try {
    const { path } = await jsonFetch('/api/pick_folder', { method: 'POST' });
    return path || null;
  } catch (e) {
    const manual = prompt(
      'Could not open folder picker. Paste the full folder path:',
      '',
    );
    return manual ? manual.trim() : null;
  }
}

function wireFolderBrowse(buttonId, inputId) {
  const btn = document.getElementById(buttonId);
  const input = document.getElementById(inputId);
  if (!btn || !input) return;
  btn.addEventListener('click', async () => {
    const path = await pickFolder();
    if (path) input.value = path;
  });
}

async function setupSetupForm() {
  const form = document.getElementById('setup-form');
  const err = document.getElementById('err');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    err.textContent = '';
    const data_root = document.getElementById('data_root').value.trim();
    try {
      await jsonFetch('/api/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data_root }),
      });
      const patch = {};
      const ics1 = document.getElementById('ics1').value.trim();
      const ics2 = document.getElementById('ics2').value.trim();
      if (ics1) patch.ics_url_studio_1 = ics1;
      if (ics2) patch.ics_url_studio_2 = ics2;
      if (Object.keys(patch).length) {
        await jsonFetch('/api/settings', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(patch),
        });
      }
      const narratorName = document.getElementById('narrator_name').value.trim();
      if (narratorName) {
        await jsonFetch('/api/narrators', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: narratorName,
            calendar_alias: document.getElementById('calendar_alias').value.trim() || null,
          }),
        });
      }
      location.href = '/library';
    } catch (e) { err.textContent = e.message; }
  });
}

const LV_ICONS = {
  library: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>',
  schedule: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>',
  narrators: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>',
  settings: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><line x1="21" y1="6" x2="14" y2="6"></line><line x1="10" y1="6" x2="3" y2="6"></line><line x1="21" y1="12" x2="12" y2="12"></line><line x1="8" y1="12" x2="3" y2="12"></line><line x1="21" y1="18" x2="16" y2="18"></line><line x1="12" y1="18" x2="3" y2="18"></line><circle cx="12" cy="6" r="2"></circle><circle cx="6" cy="12" r="2"></circle><circle cx="16" cy="18" r="2"></circle></svg>',
  brand: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>',
};

function renderSidebar(active) {
  const host = document.getElementById('lv-sidebar');
  if (!host) return;
  const items = [
    { key: 'library', label: 'Library', href: '/library' },
    { key: 'schedule', label: 'Schedule', href: '/schedule' },
    { key: 'narrators', label: 'Narrators', href: '/library?tab=narrators', tab: 'narrators' },
    { key: 'settings', label: 'Settings', href: '/settings' },
  ];
  host.innerHTML = `
    <div class="lv-brand">
      <div class="lv-brand-mark">${LV_ICONS.brand}</div>
      <span class="lv-brand-name">BookStudio</span>
    </div>
    <div class="lv-nav-label">Studio</div>
    ${items.map(it => `
      <a class="lv-nav${it.key === active ? ' active' : ''}" href="${it.href}"${it.tab ? ` data-nav-tab="${it.tab}"` : ''}>
        ${LV_ICONS[it.key]}
        ${it.label}
      </a>`).join('')}
    <div class="lv-snapshot-card">
      <div class="lv-snapshot-row">
        <span id="snapshot-dot" class="lv-snapshot-dot"></span>
        <span id="snapshot-status">Snapshot · —</span>
      </div>
      <button type="button" id="snapshot-now" class="lv-snapshot-btn">Snapshot now</button>
    </div>`;

  host.querySelectorAll('[data-nav-tab]').forEach(link => {
    link.addEventListener('click', (e) => {
      const tab = link.dataset.navTab;
      if (document.querySelector(`.lv-tab[data-tab="${tab}"]`)) {
        e.preventDefault();
        activateLibraryTab(tab);
      }
    });
  });

  setupSnapshotIndicator();
}

const libraryCounts = { books: 0, narrators: 0, publishers: 0 };

function plural(n, word) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function renderLibraryStats() {
  const el = document.getElementById('library-stats');
  if (!el) return;
  el.textContent = [
    plural(libraryCounts.books, 'book'),
    plural(libraryCounts.narrators, 'narrator'),
    plural(libraryCounts.publishers, 'publisher'),
  ].join(' · ');
}

function activateLibraryTab(target) {
  document.querySelectorAll('.lv-tab').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === target);
  });
  document.querySelectorAll('.lv-panel').forEach(p => {
    p.classList.toggle('active', p.dataset.tab === target);
  });
}

async function setupLibraryPage() {
  renderSidebar('library');
  document.querySelectorAll('.lv-tab').forEach(btn => {
    btn.addEventListener('click', () => activateLibraryTab(btn.dataset.tab));
  });

  await Promise.all([refreshNarrators(), refreshPublishers()]);
  await refreshBooks();
  setupAddBookDialog();
  document.getElementById('upload-form').addEventListener('submit', onUploadBook);
  document.getElementById('upload-url-btn').addEventListener('click', onUploadBookUrl);
  document.getElementById('filter-q').addEventListener('input', refreshBooks);
  document.getElementById('filter-status').addEventListener('change', refreshBooks);
  document.getElementById('filter-narrator').addEventListener('change', refreshBooks);
  document.getElementById('filter-publisher').addEventListener('change', refreshBooks);
  document.getElementById('narrator-create').addEventListener('submit', onCreateNarrator);
  document.getElementById('publisher-create').addEventListener('submit', onCreatePublisher);

  const wantedTab = new URLSearchParams(location.search).get('tab');
  if (wantedTab && document.querySelector(`.lv-tab[data-tab="${wantedTab}"]`)) {
    activateLibraryTab(wantedTab);
  }
}

function setupAddBookDialog() {
  const dialog = document.getElementById('add-book-dialog');
  const openBtn = document.getElementById('add-book-btn');
  const cancelBtn = document.getElementById('add-book-cancel');
  if (!dialog || !openBtn) return;
  openBtn.addEventListener('click', () => {
    document.getElementById('upload-status').textContent = '';
    dialog.showModal();
  });
  if (cancelBtn) cancelBtn.addEventListener('click', () => dialog.close());
}

function formatSnapshotAge(iso) {
  if (!iso) return 'never';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return 'unknown';
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return 'just now';
  if (mins === 1) return '1 min ago';
  return `${mins} min ago`;
}

function snapshotStatusClass(iso) {
  if (!iso) return 'stale';
  const mins = (Date.now() - new Date(iso).getTime()) / 60000;
  if (mins < 10) return 'ok';
  if (mins < 30) return 'warn';
  return 'stale';
}

function setSnapshotUi(at, hadError) {
  const el = document.getElementById('snapshot-status');
  const dot = document.getElementById('snapshot-dot');
  if (el) el.textContent = hadError ? 'Snapshot · —' : `Snapshot · ${formatSnapshotAge(at)}`;
  if (dot) {
    const cls = hadError ? 'stale' : snapshotStatusClass(at);
    dot.className = 'lv-snapshot-dot' + (cls === 'ok' ? '' : ` ${cls}`);
  }
}

async function refreshSnapshotIndicator() {
  if (!document.getElementById('snapshot-status')) return;
  try {
    const hb = await jsonFetch('/api/heartbeat');
    setSnapshotUi(hb.last_snapshot_at, false);
  } catch (_) {
    setSnapshotUi(null, true);
  }
}

function setupSnapshotIndicator() {
  const btn = document.getElementById('snapshot-now');
  if (!btn) return;
  refreshSnapshotIndicator();
  setInterval(refreshSnapshotIndicator, 30000);
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      await jsonFetch('/api/snapshot', { method: 'POST' });
      await refreshSnapshotIndicator();
    } catch (e) {
      const el = document.getElementById('snapshot-status');
      if (el) el.textContent = e.message;
    } finally {
      btn.disabled = false;
    }
  });
}

const STATUS_META = {
  planned: { label: 'Planned', dot: '#a1a1aa', bar: '#d4d4d8' },
  in_progress: { label: 'In progress', dot: 'var(--lv-accent)', bar: 'var(--lv-accent)' },
  done: { label: 'Done', dot: '#16a34a', bar: '#16a34a' },
  archived: { label: 'Archived', dot: '#d4d4d8', bar: '#d4d4d8' },
};

function bookProgress(b) {
  if (b.pages && b.pages > 0) {
    return Math.max(0, Math.min(100, Math.round((b.current_page / b.pages) * 100)));
  }
  return (b.status === 'done' || b.status === 'archived') ? 100 : 0;
}

async function refreshBooks() {
  const params = new URLSearchParams();
  const q = document.getElementById('filter-q').value.trim();
  const s = document.getElementById('filter-status').value;
  const nid = document.getElementById('filter-narrator').value;
  const pid = document.getElementById('filter-publisher').value;
  if (q) params.set('q', q);
  if (s) params.set('status', s);
  if (nid) params.set('narrator_id', nid);
  if (pid) params.set('publisher_id', pid);
  const url = '/api/books' + (params.toString() ? '?' + params : '');
  const { books } = await jsonFetch(url);
  libraryCounts.books = books.length;
  renderLibraryStats();
  const tbody = document.querySelector('#books-table tbody');
  if (!books.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="lv-empty">No books match.</td></tr>';
    return;
  }
  const narratorMap = Object.fromEntries(
    [...document.getElementById('filter-narrator').options].map(o => [o.value, o.textContent])
  );
  const publisherMap = Object.fromEntries(
    [...document.getElementById('filter-publisher').options].map(o => [o.value, o.textContent])
  );
  tbody.innerHTML = books.map(b => {
    const meta = STATUS_META[b.status] || { label: b.status, dot: '#a1a1aa', bar: '#d4d4d8' };
    const pct = bookProgress(b);
    return `
    <tr class="lv-row" onclick="location.href='/books/${b.id}'">
      <td class="lv-cell-title">${escapeHtml(b.title)}</td>
      <td><span class="lv-badge">${escapeHtml(b.format || '—')}</span></td>
      <td>${b.narrator_id ? escapeHtml(narratorMap[String(b.narrator_id)] || '—') : '—'}</td>
      <td class="lv-cell-sub">${b.publisher_id ? escapeHtml(publisherMap[String(b.publisher_id)] || '—') : '—'}</td>
      <td>
        <span class="lv-status">
          <span class="lv-status-dot" style="background:${meta.dot}"></span>
          <span class="lv-status-label">${meta.label}</span>
        </span>
      </td>
      <td class="lv-cell-num">${b.pages || '—'}</td>
      <td>
        <span class="lv-progress">
          <span class="lv-progress-track">
            <span class="lv-progress-fill" style="width:${pct}%;background:${meta.bar}"></span>
          </span>
          <span class="lv-progress-label">${pct}%</span>
        </span>
      </td>
    </tr>`;
  }).join('');
}

async function refreshNarrators() {
  const { narrators } = await jsonFetch('/api/narrators');
  libraryCounts.narrators = narrators.length;
  renderLibraryStats();
  const tbody = document.querySelector('#narrators-table tbody');
  tbody.innerHTML = narrators.length
    ? narrators.map(n => `
      <tr class="lv-row" onclick="location.href='/narrators/${n.id}'">
        <td class="lv-cell-title">${escapeHtml(n.name)}</td>
        <td>${escapeHtml(n.calendar_alias || '—')}</td>
        <td class="lv-cell-sub">${escapeHtml(n.notes || '')}</td>
      </tr>`).join('')
    : '<tr><td colspan="3" class="lv-empty">No narrators yet.</td></tr>';
  const sel = document.getElementById('filter-narrator');
  const current = sel.value;
  sel.innerHTML = '<option value="">Any narrator</option>' +
    narrators.map(n => `<option value="${n.id}">${escapeHtml(n.name)}</option>`).join('');
  sel.value = current;
}

async function refreshPublishers() {
  const { publishers } = await jsonFetch('/api/publishers');
  libraryCounts.publishers = publishers.length;
  renderLibraryStats();
  const tbody = document.querySelector('#publishers-table tbody');
  tbody.innerHTML = publishers.length
    ? publishers.map(p => `
      <tr>
        <td class="lv-cell-title">${escapeHtml(p.name)}</td>
        <td class="lv-cell-sub">${escapeHtml(p.notes || '')}</td>
      </tr>`).join('')
    : '<tr><td colspan="2" class="lv-empty">No publishers yet.</td></tr>';
  const sel = document.getElementById('filter-publisher');
  const current = sel.value;
  sel.innerHTML = '<option value="">Any publisher</option>' +
    publishers.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
  sel.value = current;
}

async function onUploadBook(e) {
  e.preventDefault();
  const status = document.getElementById('upload-status');
  const file = document.getElementById('file').files[0];
  if (!file) {
    status.textContent = 'Choose a file or use URL import below.';
    return;
  }
  status.textContent = 'Uploading…';
  const fd = new FormData();
  fd.append('title', document.getElementById('title').value);
  fd.append('file', file);
  try {
    const r = await fetch('/api/books', { method: 'POST', body: fd });
    if (!r.ok) throw new Error(await r.text());
    const book = await r.json();
    status.textContent = 'Done.';
    document.getElementById('upload-form').reset();
    location.href = `/books/${book.id}`;
  } catch (e) { status.textContent = e.message; }
}

async function onUploadBookUrl() {
  const status = document.getElementById('upload-status');
  const title = document.getElementById('title').value.trim();
  const url = document.getElementById('source-url').value.trim();
  if (!title || !url) {
    status.textContent = 'Enter book title and URL.';
    return;
  }
  status.textContent = 'Downloading…';
  try {
    const book = await jsonFetch('/api/books/from_url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, url }),
    });
    status.textContent = 'Done.';
    document.getElementById('upload-form').reset();
    location.href = `/books/${book.id}`;
  } catch (e) { status.textContent = e.message; }
}

async function onCreateNarrator(e) {
  e.preventDefault();
  const status = document.getElementById('nc-status');
  status.textContent = 'Saving…';
  try {
    await jsonFetch('/api/narrators', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: document.getElementById('nc-name').value,
        calendar_alias: document.getElementById('nc-alias').value || null,
      }),
    });
    document.getElementById('narrator-create').reset();
    status.textContent = '';
    await refreshNarrators();
    await refreshBooks();
  } catch (e) { status.textContent = e.message; }
}

async function onCreatePublisher(e) {
  e.preventDefault();
  const status = document.getElementById('pc-status');
  status.textContent = 'Saving…';
  try {
    await jsonFetch('/api/publishers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: document.getElementById('pc-name').value,
        notes: document.getElementById('pc-notes').value || null,
      }),
    });
    document.getElementById('publisher-create').reset();
    status.textContent = '';
    await refreshPublishers();
    await refreshBooks();
  } catch (e) { status.textContent = e.message; }
}

async function setupBookPage() {
  const id = location.pathname.split('/').pop();
  const [b, narrators, publishers, allBooks] = await Promise.all([
    jsonFetch(`/api/books/${id}`),
    jsonFetch('/api/narrators'),
    jsonFetch('/api/publishers'),
    jsonFetch('/api/books'),
  ]);

  document.getElementById('title').textContent = b.title;
  document.getElementById('meta').textContent = `Slug: ${b.slug}`;
  document.getElementById('open-viewer').addEventListener('click', () => {
    if (b.is_draft && !confirm('This book is an incomplete draft. Open in viewer anyway?')) {
      return;
    }
    location.href = `/live/${id}`;
  });

  const splitDialog = document.getElementById('split-dialog');
  const splitSelect = document.getElementById('split-book-id');
  splitSelect.innerHTML = allBooks.books
    .filter((book) => String(book.id) !== String(id))
    .map((book) => `<option value="${book.id}">${escapeHtml(book.title)}</option>`)
    .join('');
  document.getElementById('open-split').addEventListener('click', () => {
    if (!splitSelect.options.length) {
      alert('No other books in the library yet.');
      return;
    }
    splitDialog.showModal();
  });
  document.getElementById('cancel-split').addEventListener('click', () => splitDialog.close());
  document.getElementById('split-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const otherId = splitSelect.value;
    if (!otherId) return;
    location.href = `/live/${id}/${otherId}`;
  });

  document.getElementById('delete-book').addEventListener('click', async () => {
    if (!confirm(`Delete “${b.title}” from the library? This cannot be undone.`)) return;
    try {
      await jsonFetch(`/api/books/${id}`, { method: 'DELETE' });
      location.href = '/library';
    } catch (e) {
      alert(e.message);
    }
  });

  wireFolderBrowse('browse-audio', 'f-audio');
  document.getElementById('format').textContent = b.format;
  document.getElementById('pages').textContent = b.pages || '—';
  document.getElementById('body_chars').textContent = b.body_chars.toLocaleString();
  document.getElementById('cpp').textContent = b.chars_per_page || '—';

  function fmtHours(seconds) { return seconds > 0 ? (seconds / 3600).toFixed(2) : '—'; }
  function fmtRound(x) { return x > 0 ? Math.round(x).toLocaleString() : '—'; }
  function fmtPct(x) { return x > 0 ? (x * 100).toFixed(1) + '%' : '—'; }

  const stats = b.stats || {};
  document.getElementById('h_recorded').textContent = fmtHours(stats.total_audio_seconds || 0);
  document.getElementById('chars_per_hour').textContent = fmtRound(stats.chars_per_hour || 0);
  document.getElementById('pages_per_hour').textContent = fmtRound(stats.pages_per_hour || 0);
  document.getElementById('progress_pct').textContent = fmtPct(stats.progress_pct || 0);

  document.getElementById('rescan-audio').addEventListener('click', async () => {
    const status = document.getElementById('rescan-status');
    status.textContent = 'Scanning…';
    try {
      const r = await jsonFetch(`/api/books/${id}/rescan_audio`, { method: 'POST' });
      status.textContent = `${r.audio_files} file(s).`;
      const refreshed = await jsonFetch(`/api/books/${id}`);
      const s = refreshed.stats || {};
      document.getElementById('h_recorded').textContent = fmtHours(s.total_audio_seconds || 0);
      document.getElementById('chars_per_hour').textContent = fmtRound(s.chars_per_hour || 0);
      document.getElementById('pages_per_hour').textContent = fmtRound(s.pages_per_hour || 0);
      document.getElementById('progress_pct').textContent = fmtPct(s.progress_pct || 0);
    } catch (e) { status.textContent = e.message; }
  });

  document.getElementById('source_path').textContent = b.source_path;
  document.getElementById('f-status').value = b.status;
  document.getElementById('f-genre').value = b.genre || '';
  document.getElementById('f-planned-end').value = b.planned_end || '';
  document.getElementById('f-notes').value = b.publisher_notes || '';
  document.getElementById('f-audio').value = b.audio_folder || '';

  const nsel = document.getElementById('f-narrator');
  function fillNarratorSelect(selectedId) {
    nsel.innerHTML = '<option value="">Unassigned</option>' +
      narrators.narrators.map(n => `<option value="${n.id}">${escapeHtml(n.name)}</option>`).join('');
    nsel.value = selectedId == null ? '' : String(selectedId);
  }
  fillNarratorSelect(b.narrator_id);

  const psel = document.getElementById('f-publisher');
  function fillPublisherSelect(selectedId) {
    psel.innerHTML = '<option value="">None</option>' +
      publishers.publishers.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
    psel.value = selectedId == null ? '' : String(selectedId);
  }
  fillPublisherSelect(b.publisher_id);

  const narratorDialog = document.getElementById('add-narrator-dialog');
  document.getElementById('add-narrator-btn').addEventListener('click', () => narratorDialog.showModal());
  document.getElementById('cancel-narrator').addEventListener('click', () => narratorDialog.close());
  document.getElementById('add-narrator-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const created = await jsonFetch('/api/narrators', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: document.getElementById('new-narrator-name').value.trim(),
          calendar_alias: document.getElementById('new-narrator-alias').value.trim() || null,
        }),
      });
      narrators.narrators.push(created);
      fillNarratorSelect(created.id);
      narratorDialog.close();
      document.getElementById('add-narrator-form').reset();
    } catch (err) {
      alert(err.message);
    }
  });

  const publisherDialog = document.getElementById('add-publisher-dialog');
  document.getElementById('add-publisher-btn').addEventListener('click', () => publisherDialog.showModal());
  document.getElementById('cancel-publisher').addEventListener('click', () => publisherDialog.close());
  document.getElementById('add-publisher-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const created = await jsonFetch('/api/publishers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: document.getElementById('new-publisher-name').value.trim(),
          notes: document.getElementById('new-publisher-notes').value.trim() || null,
        }),
      });
      publishers.publishers.push(created);
      fillPublisherSelect(created.id);
      publisherDialog.close();
      document.getElementById('add-publisher-form').reset();
    } catch (err) {
      alert(err.message);
    }
  });

  if (b.is_draft) {
    document.getElementById('draft-banner').style.display = 'block';
    document.getElementById('clear-draft').style.display = 'inline';
  }

  document.getElementById('book-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    await savePatch({});
  });

  document.getElementById('clear-draft').addEventListener('click', async () => {
    await savePatch({ is_draft: false });
  });

  async function savePatch(extra) {
    const status = document.getElementById('save-status');
    status.textContent = 'Saving…';
    const payload = {
      status: document.getElementById('f-status').value,
      genre: document.getElementById('f-genre').value || null,
      planned_end: document.getElementById('f-planned-end').value || null,
      publisher_notes: document.getElementById('f-notes').value || null,
      audio_folder: document.getElementById('f-audio').value || null,
      narrator_id: nsel.value ? Number(nsel.value) : null,
      publisher_id: psel.value ? Number(psel.value) : null,
      ...extra,
    };
    try {
      const updated = await jsonFetch(`/api/books/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      status.textContent = 'Saved.';
      if (!updated.is_draft) {
        document.getElementById('draft-banner').style.display = 'none';
        document.getElementById('clear-draft').style.display = 'none';
      }
    } catch (e) { status.textContent = e.message; }
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

async function setupSettingsPage() {
  /* settings page logic lives in settings.js */
}

async function setupNarratorPage() {
  const nid = location.pathname.split('/').pop();
  const n = await jsonFetch(`/api/narrators/${nid}`);
  document.getElementById('name').textContent = n.name;
  document.getElementById('f-name').value = n.name;
  document.getElementById('f-alias').value = n.calendar_alias || '';
  document.getElementById('f-notes').value = n.notes || '';

  document.getElementById('narrator-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const status = document.getElementById('save-status');
    status.textContent = 'Saving…';
    const body = {
      name: document.getElementById('f-name').value,
      calendar_alias: document.getElementById('f-alias').value || null,
      notes: document.getElementById('f-notes').value || null,
    };
    try {
      const updated = await jsonFetch(`/api/narrators/${nid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      document.getElementById('name').textContent = updated.name;
      status.textContent = 'Saved.';
    } catch (e) { status.textContent = e.message; }
  });

  const stats = n.stats || {};
  document.getElementById('s-assigned').textContent = stats.books_assigned || 0;
  document.getElementById('s-done').textContent = stats.books_done || 0;
  document.getElementById('s-hours').textContent =
    stats.total_audio_seconds > 0 ? (stats.total_audio_seconds / 3600).toFixed(2) : '—';
  document.getElementById('s-cph').textContent =
    stats.avg_chars_per_hour > 0 ? Math.round(stats.avg_chars_per_hour).toLocaleString() : '—';
  document.getElementById('s-pph').textContent =
    stats.avg_pages_per_hour > 0 ? Math.round(stats.avg_pages_per_hour).toLocaleString() : '—';

  const upcoming = n.upcoming_sessions || [];
  const upcomingBody = document.querySelector('#upcoming-table tbody');
  upcomingBody.innerHTML = upcoming.length
    ? upcoming.map((s) => `
      <tr>
        <td>${s.start_time || '—'}</td>
        <td>${escapeHtml(s.source)}</td>
        <td>${escapeHtml(s.raw_title)}</td>
        <td>${escapeHtml(s.action_status)}</td>
      </tr>`).join('')
    : '<tr><td colspan="4" class="muted">No upcoming sessions.</td></tr>';

  const history = n.history || [];
  const histBody = document.querySelector('#history-table tbody');
  histBody.innerHTML = history.length
    ? history.map(h => `
      <tr onclick="location.href='/books/${h.book_id}'" style="cursor:pointer">
        <td>${escapeHtml(h.title)}</td>
        <td>${h.assigned_at || '—'}</td>
        <td>${h.finished_at || '<span class="muted">active</span>'}</td>
      </tr>`).join('')
    : '<tr><td colspan="3" class="muted">No history yet.</td></tr>';

  const { books } = await jsonFetch(`/api/books?narrator_id=${nid}`);
  const currentBody = document.querySelector('#current-table tbody');
  const current = books.filter(b => b.status === 'in_progress');
  if (!current.length) {
    currentBody.innerHTML = '<tr><td colspan="3" class="muted">No active books.</td></tr>';
  } else {
    currentBody.innerHTML = current.map(b => `
      <tr onclick="location.href='/books/${b.id}'" style="cursor:pointer">
        <td>${escapeHtml(b.title)}</td>
        <td>${b.pages ? `${b.current_page}/${b.pages}` : `page ${b.current_page}`}</td>
        <td>${b.planned_end || '—'}</td>
      </tr>`).join('');
  }
}
