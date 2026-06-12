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
  const form = document.getElementById('upload-form');
  const status = document.getElementById('upload-status');
  const tbody = document.querySelector('#books-table tbody');

  async function refresh() {
    const { books } = await jsonFetch('/api/books');
    if (!books.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="muted">No books yet.</td></tr>';
      return;
    }
    tbody.innerHTML = books.map(b => `
      <tr onclick="location.href='/books/${b.id}'" style="cursor:pointer">
        <td>${escapeHtml(b.title)}</td>
        <td>${b.format}</td>
        <td>${b.pages || '—'}</td>
        <td>${b.body_chars.toLocaleString()}</td>
        <td>${b.status}</td>
      </tr>`).join('');
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    status.textContent = 'Uploading…';
    const fd = new FormData();
    fd.append('title', document.getElementById('title').value);
    fd.append('file', document.getElementById('file').files[0]);
    try {
      const r = await fetch('/api/books', { method: 'POST', body: fd });
      if (!r.ok) throw new Error(await r.text());
      status.textContent = 'Done.';
      form.reset();
      await refresh();
    } catch (e) {
      status.textContent = e.message;
    }
  });

  await refresh();
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
