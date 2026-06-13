async function jsonFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  if (r.status === 204) return null;
  return r.json();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function localInputToIso(value) {
  if (!value) return '';
  return new Date(value).toISOString();
}

function formatWhen(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function isToday(iso) {
  const d = new Date(iso);
  const now = new Date();
  return d.getFullYear() === now.getFullYear()
    && d.getMonth() === now.getMonth()
    && d.getDate() === now.getDate();
}

let scheduleItems = [];
let activeItem = null;
let jitItemId = null;

async function loadSchedule() {
  const status = document.getElementById('schedule-status');
  try {
    const { items } = await jsonFetch('/api/schedule');
    scheduleItems = items;
    renderList();
    renderLanes();
    status.textContent = `${items.length} item(s) loaded.`;
  } catch (e) {
    status.textContent = e.message;
  }
}

function renderList() {
  const tbody = document.querySelector('#schedule-table tbody');
  if (!scheduleItems.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="muted">No schedule items.</td></tr>';
    return;
  }
  tbody.innerHTML = scheduleItems.map((item) => `
    <tr data-id="${item.id}">
      <td>${escapeHtml(formatWhen(item.start_time))}</td>
      <td>${escapeHtml(item.source)}</td>
      <td>${escapeHtml(item.kind || '—')}</td>
      <td>${escapeHtml(item.raw_title)}</td>
      <td>${escapeHtml(item.resolved_narrator_name || '—')}</td>
      <td>${escapeHtml(item.resolved_book_title || '—')}</td>
      <td>${escapeHtml(item.action_status)}</td>
      <td><button type="button" data-start="${item.id}">Start</button></td>
    </tr>`).join('');
  tbody.querySelectorAll('[data-start]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      startSession(Number(btn.dataset.start));
    });
  });
  tbody.querySelectorAll('tr[data-id]').forEach((row) => {
    row.addEventListener('click', () => {
      const id = Number(row.dataset.id);
      openItemModal(scheduleItems.find((i) => i.id === id));
    });
  });
}

function renderLanes() {
  document.querySelectorAll('.lane').forEach((lane) => {
    const source = lane.dataset.source;
    const host = lane.querySelector('.lane-items');
    const items = scheduleItems.filter((i) => i.source === source);
    if (!items.length) {
      host.innerHTML = '<p class="muted">No items.</p>';
      return;
    }
    host.innerHTML = items.map((item) => `
      <div class="lane-item source-${item.source}${isToday(item.start_time) ? ' today' : ''}"
           data-id="${item.id}">
        <strong>${escapeHtml(item.raw_title)}</strong>
        <div class="muted">${escapeHtml(formatWhen(item.start_time))}</div>
        <button type="button" data-start="${item.id}">Start Session</button>
      </div>`).join('');
    host.querySelectorAll('.lane-item').forEach((el) => {
      el.addEventListener('click', (e) => {
        if (e.target.tagName === 'BUTTON') return;
        openItemModal(scheduleItems.find((i) => i.id === Number(el.dataset.id)));
      });
    });
    host.querySelectorAll('[data-start]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        startSession(Number(btn.dataset.start));
      });
    });
  });
}

function openItemModal(item) {
  if (!item) return;
  activeItem = item;
  document.getElementById('modal-title').textContent = item.raw_title;
  const mirror = item.google_event_id != null;
  document.getElementById('modal-body').innerHTML = `
    <p><strong>Source:</strong> ${escapeHtml(item.source)}</p>
    <p><strong>When:</strong> ${escapeHtml(formatWhen(item.start_time))} – ${escapeHtml(formatWhen(item.end_time))}</p>
    <p><strong>Status:</strong> ${escapeHtml(item.action_status)}</p>
    ${mirror ? '<p class="muted">Calendar-mirrored row (title/times read-only).</p>' : ''}
    <label>Notes<br><textarea id="modal-notes" rows="2">${escapeHtml(item.notes || '')}</textarea></label>
    ${mirror ? '' : `
      <label>Title<br><input id="modal-raw-title" value="${escapeHtml(item.raw_title)}"></label>
    `}
    <label>Action status
      <select id="modal-status">
        ${['pending','started','completed','skipped','cancelled'].map((s) =>
    `<option value="${s}"${s === item.action_status ? ' selected' : ''}>${s}</option>`).join('')}
      </select>
    </label>`;
  document.getElementById('modal-backdrop').classList.remove('hidden');
}

async function saveModalItem() {
  if (!activeItem) return;
  const payload = {
    action_status: document.getElementById('modal-status').value,
    notes: document.getElementById('modal-notes').value || null,
  };
  const titleInput = document.getElementById('modal-raw-title');
  if (titleInput) payload.raw_title = titleInput.value;
  await jsonFetch(`/api/schedule/${activeItem.id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  await loadSchedule();
}

async function startSession(itemId, bookId = null) {
  const status = document.getElementById('schedule-status');
  status.textContent = 'Starting session…';
  try {
    const body = bookId != null ? { book_id: bookId } : {};
    const result = await jsonFetch(`/api/schedule/${itemId}/start_session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (result.mode === 'A') {
      location.href = `/live/${result.book_id}?session_id=${result.session_id}`;
      return;
    }
    if (result.mode === 'B') {
      showBookPicker(itemId, result.candidate_books);
      status.textContent = 'Choose a book to continue.';
      return;
    }
    openJitWizard(itemId, result.raw_title);
    status.textContent = '';
  } catch (e) {
    status.textContent = e.message;
  }
}

function showBookPicker(itemId, books) {
  const host = document.getElementById('book-picker');
  host.innerHTML = books.map((b) => `
    <button type="button" class="picker-book" data-id="${b.id}">${escapeHtml(b.title)}</button>
  `).join('');
  document.getElementById('picker-backdrop').classList.remove('hidden');
  host.querySelectorAll('.picker-book').forEach((btn) => {
    btn.addEventListener('click', async () => {
      document.getElementById('picker-backdrop').classList.add('hidden');
      await startSession(itemId, Number(btn.dataset.id));
    });
  });
}

async function openJitWizard(itemId, rawTitle) {
  jitItemId = itemId;
  document.getElementById('jit-event-title').textContent = rawTitle || '';
  document.getElementById('jit-title').value = rawTitle || '';
  const { narrators } = await jsonFetch('/api/narrators');
  const sel = document.getElementById('jit-narrator');
  sel.innerHTML = '<option value="">+ Create new narrator</option>'
    + narrators.map((n) => `<option value="${n.id}">${escapeHtml(n.name)}</option>`).join('');
  document.getElementById('jit-new-narrator-wrap').classList.toggle('hidden', sel.value !== '');
  document.getElementById('jit-narrator-name').value = rawTitle || '';
  document.getElementById('jit-backdrop').classList.remove('hidden');
}

async function submitJitForm(e) {
  e.preventDefault();
  const form = new FormData();
  const narratorSel = document.getElementById('jit-narrator');
  if (narratorSel.value) {
    form.append('narrator_id', narratorSel.value);
  } else {
    form.append('narrator_name', document.getElementById('jit-narrator-name').value.trim());
    if (document.getElementById('jit-link-alias').checked) {
      form.append('link_future_events', 'true');
      const alias = document.getElementById('jit-alias').value.trim();
      if (alias) form.append('calendar_alias', alias);
    }
  }
  form.append('title', document.getElementById('jit-title').value.trim());
  const audio = document.getElementById('jit-audio').value.trim();
  if (audio) form.append('audio_folder', audio);
  const file = document.getElementById('jit-file').files[0];
  if (!file) return;
  form.append('file', file);
  const result = await jsonFetch(`/api/schedule/${jitItemId}/jit`, {
    method: 'POST',
    body: form,
  });
  location.href = `/live/${result.book_id}?session_id=${result.session_id}`;
}

function setupSchedulePage() {
  document.getElementById('view-list').addEventListener('click', () => {
    document.getElementById('view-list').classList.add('active');
    document.getElementById('view-lanes').classList.remove('active');
    document.getElementById('list-view').classList.add('active');
    document.getElementById('lanes-view').classList.remove('active');
  });
  document.getElementById('view-lanes').addEventListener('click', () => {
    document.getElementById('view-lanes').classList.add('active');
    document.getElementById('view-list').classList.remove('active');
    document.getElementById('lanes-view').classList.add('active');
    document.getElementById('list-view').classList.remove('active');
  });
  document.getElementById('refresh-calendars').addEventListener('click', async () => {
    const status = document.getElementById('schedule-status');
    status.textContent = 'Syncing calendars…';
    try {
      const r = await jsonFetch('/api/schedule/refresh', { method: 'POST' });
      status.textContent = `Synced at ${r.synced_at || 'now'}.`;
      await loadSchedule();
    } catch (e) { status.textContent = e.message; }
  });
  document.getElementById('manual-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    await jsonFetch('/api/schedule', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: 'manual',
        kind: document.getElementById('m-kind').value,
        raw_title: document.getElementById('m-title').value.trim(),
        start_time: localInputToIso(document.getElementById('m-start').value),
        end_time: localInputToIso(document.getElementById('m-end').value),
      }),
    });
    e.target.reset();
    await loadSchedule();
  });
  document.getElementById('modal-close').addEventListener('click', () => {
    document.getElementById('modal-backdrop').classList.add('hidden');
  });
  document.getElementById('modal-start').addEventListener('click', async () => {
    if (activeItem) await startSession(activeItem.id);
  });
  document.getElementById('modal-backdrop').addEventListener('click', async (e) => {
    if (e.target.id === 'modal-backdrop') {
      try { await saveModalItem(); } catch (_) { /* ignore save errors on backdrop close */ }
      document.getElementById('modal-backdrop').classList.add('hidden');
    }
  });
  document.getElementById('picker-cancel').addEventListener('click', () => {
    document.getElementById('picker-backdrop').classList.add('hidden');
  });
  document.getElementById('jit-cancel').addEventListener('click', () => {
    document.getElementById('jit-backdrop').classList.add('hidden');
  });
  document.getElementById('jit-form').addEventListener('submit', async (e) => {
    try { await submitJitForm(e); } catch (err) {
      document.getElementById('schedule-status').textContent = err.message;
    }
  });
  document.getElementById('jit-narrator').addEventListener('change', (e) => {
    document.getElementById('jit-new-narrator-wrap').classList.toggle('hidden', e.target.value !== '');
  });
  loadSchedule();
}

setupSchedulePage();
