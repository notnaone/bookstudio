async function setupSettingsPage() {
  const status = document.getElementById('status');
  const settings = await jsonFetch('/api/settings');

  const fields = {
    data_root: 'data_root',
    ics_url_studio_1: 'ics1',
    ics_url_studio_2: 'ics2',
    pace_unit: 'pace_unit',
    snapshot_interval_seconds: 'snapshot_interval',
    audio_scan_interval_seconds: 'audio_scan_interval',
    calendar_poll_interval_seconds: 'calendar_poll_interval',
    reaper_interval_seconds: 'reaper_interval',
    session_idle_timeout_seconds: 'session_idle_timeout',
  };

  for (const [key, id] of Object.entries(fields)) {
    const el = document.getElementById(id);
    if (!el || settings[key] == null) continue;
    el.value = settings[key];
  }

  const original = {};
  for (const [key, id] of Object.entries(fields)) {
    const el = document.getElementById(id);
    if (el) original[key] = el.value;
  }

  document.getElementById('settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    status.textContent = 'Saving…';
    const payload = {};
    for (const [key, id] of Object.entries(fields)) {
      const el = document.getElementById(id);
      if (!el) continue;
      const val = el.value.trim();
      if (val !== String(original[key] ?? '')) {
        payload[key] = val;
      }
    }
    if (!Object.keys(payload).length) {
      status.textContent = 'No changes.';
      return;
    }
    try {
      const updated = await jsonFetch('/api/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      for (const [key, id] of Object.entries(fields)) {
        const el = document.getElementById(id);
        if (el && updated[key] != null) {
          el.value = updated[key];
          original[key] = String(updated[key]);
        }
      }
      status.textContent = 'Saved.';
    } catch (err) {
      status.textContent = err.message;
    }
  });

  document.getElementById('sync-now').addEventListener('click', async () => {
    status.textContent = 'Syncing calendars…';
    try {
      if (
        document.getElementById('ics1').value !== original.ics_url_studio_1
        || document.getElementById('ics2').value !== original.ics_url_studio_2
      ) {
        await jsonFetch('/api/settings', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ics_url_studio_1: document.getElementById('ics1').value.trim(),
            ics_url_studio_2: document.getElementById('ics2').value.trim(),
          }),
        });
      }
      const r = await jsonFetch('/api/schedule/refresh', { method: 'POST' });
      status.textContent = `Synced at ${r.synced_at || 'now'}.`;
    } catch (err) {
      status.textContent = err.message;
    }
  });

  const snapStatus = document.getElementById('maint-snapshot-status');
  document.getElementById('maint-snapshot-now').addEventListener('click', async () => {
    snapStatus.textContent = 'Snapshotting…';
    try {
      const r = await jsonFetch('/api/snapshot', { method: 'POST' });
      snapStatus.textContent = `Done (${r.bytes || 0} bytes).`;
    } catch (err) {
      snapStatus.textContent = err.message;
    }
  });

  document.getElementById('cleanup-exports').addEventListener('click', async () => {
    const el = document.getElementById('cleanup-status');
    const days = Number(document.getElementById('cleanup-days').value);
    el.textContent = 'Cleaning…';
    try {
      const r = await jsonFetch('/api/export/cleanup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ older_than_days: days }),
      });
      el.textContent = `Deleted ${r.deleted} file(s).`;
    } catch (err) {
      el.textContent = err.message;
    }
  });

  document.getElementById('restore-marks').addEventListener('click', async () => {
    const el = document.getElementById('restore-status');
    el.textContent = 'Restoring…';
    try {
      const r = await jsonFetch('/api/marks/restore', { method: 'POST' });
      el.textContent = `Restored ${r.restored}, skipped ${r.skipped_existing}.`;
      if (r.errors && r.errors.length) {
        el.textContent += ` ${r.errors.length} error(s).`;
      }
    } catch (err) {
      el.textContent = err.message;
    }
  });
}

setupSettingsPage();
