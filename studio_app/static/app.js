async function jsonFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
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
      location.href = '/library';
    } catch (e) { err.textContent = e.message; }
  });
}

async function setupLibraryPage() {
  document.querySelectorAll('.tabs button').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const target = btn.dataset.tab;
      document.querySelectorAll('.tab-panel').forEach(p => {
        p.classList.toggle('active', p.dataset.tab === target);
      });
    });
  });

  await Promise.all([refreshBooks(), refreshNarrators(), refreshPublishers()]);
  document.getElementById('upload-form').addEventListener('submit', onUploadBook);
  document.getElementById('filter-q').addEventListener('input', refreshBooks);
  document.getElementById('filter-status').addEventListener('change', refreshBooks);
  document.getElementById('filter-narrator').addEventListener('change', refreshBooks);
  document.getElementById('filter-publisher').addEventListener('change', refreshBooks);
  document.getElementById('narrator-create').addEventListener('submit', onCreateNarrator);
  document.getElementById('publisher-create').addEventListener('submit', onCreatePublisher);
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
  const tbody = document.querySelector('#books-table tbody');
  if (!books.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">No books match.</td></tr>';
    return;
  }
  const narratorMap = Object.fromEntries(
    [...document.getElementById('filter-narrator').options].map(o => [o.value, o.textContent])
  );
  tbody.innerHTML = books.map(b => `
    <tr onclick="location.href='/books/${b.id}'" style="cursor:pointer">
      <td>${escapeHtml(b.title)}</td>
      <td>${b.format}</td>
      <td>${b.narrator_id ? escapeHtml(narratorMap[String(b.narrator_id)] || '—') : '—'}</td>
      <td>${b.status}</td>
      <td>${b.pages || '—'}</td>
    </tr>`).join('');
}

async function refreshNarrators() {
  const { narrators } = await jsonFetch('/api/narrators');
  const tbody = document.querySelector('#narrators-table tbody');
  tbody.innerHTML = narrators.length
    ? narrators.map(n => `
      <tr onclick="location.href='/narrators/${n.id}'" style="cursor:pointer">
        <td>${escapeHtml(n.name)}</td>
        <td>${escapeHtml(n.calendar_alias || '—')}</td>
        <td>${escapeHtml(n.notes || '')}</td>
      </tr>`).join('')
    : '<tr><td colspan="3" class="muted">No narrators yet.</td></tr>';
  const sel = document.getElementById('filter-narrator');
  const current = sel.value;
  sel.innerHTML = '<option value="">Any narrator</option>' +
    narrators.map(n => `<option value="${n.id}">${escapeHtml(n.name)}</option>`).join('');
  sel.value = current;
}

async function refreshPublishers() {
  const { publishers } = await jsonFetch('/api/publishers');
  const tbody = document.querySelector('#publishers-table tbody');
  tbody.innerHTML = publishers.length
    ? publishers.map(p => `
      <tr>
        <td>${escapeHtml(p.name)}</td>
        <td>${escapeHtml(p.notes || '')}</td>
      </tr>`).join('')
    : '<tr><td colspan="2" class="muted">No publishers yet.</td></tr>';
  const sel = document.getElementById('filter-publisher');
  const current = sel.value;
  sel.innerHTML = '<option value="">Any publisher</option>' +
    publishers.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
  sel.value = current;
}

async function onUploadBook(e) {
  e.preventDefault();
  const status = document.getElementById('upload-status');
  status.textContent = 'Uploading…';
  const fd = new FormData();
  fd.append('title', document.getElementById('title').value);
  fd.append('file', document.getElementById('file').files[0]);
  try {
    const r = await fetch('/api/books', { method: 'POST', body: fd });
    if (!r.ok) throw new Error(await r.text());
    status.textContent = 'Done.';
    document.getElementById('upload-form').reset();
    await refreshBooks();
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
  const b = await jsonFetch(`/api/books/${id}`);
  document.getElementById('title').textContent = b.title;
  document.getElementById('meta').textContent = `Slug: ${b.slug}`;
  document.getElementById('format').textContent = b.format;
  document.getElementById('pages').textContent = b.pages || '—';
  document.getElementById('body_chars').textContent = b.body_chars.toLocaleString();
  document.getElementById('raw_chars').textContent = b.raw_chars.toLocaleString();
  document.getElementById('cpp').textContent = b.chars_per_page || '—';
  document.getElementById('images').textContent = b.images;
  document.getElementById('status').textContent = b.status;
  document.getElementById('source_path').textContent = b.source_path;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
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
