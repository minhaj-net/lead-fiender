/**
 * popup.js — Codeloom Lead Finder Extension
 *
 * Connects the popup UI to the local FastAPI backend.
 * Uses fetch() to call http://127.0.0.1:8000/...
 *
 * Flow:
 *   1. On open → health check → show status
 *   2. START → POST /automation/start → poll /automation/status
 *   3. STOP  → POST /automation/stop
 *   4. EXPORT → GET /leads/export
 */

'use strict';

const API = 'http://127.0.0.1:8000';
const POLL_INTERVAL_MS = 2500;

// ── DOM refs ─────────────────────────────────────────────────────────────────
const statusBar        = document.getElementById('status-bar');
const statusDot        = document.getElementById('status-dot');
const statusText       = document.getElementById('status-text');
const statusDetail     = document.getElementById('status-detail');
const statFound        = document.getElementById('stat-found');
const statQualified    = document.getElementById('stat-qualified');
const statSkipped      = document.getElementById('stat-skipped');
const keywordInput     = document.getElementById('search-keyword');
const locationInput    = document.getElementById('search-location');
const btnStart         = document.getElementById('btn-start');
const btnStop          = document.getElementById('btn-stop');
const btnExport        = document.getElementById('btn-export');
const progressSection  = document.getElementById('progress-section');
const progressBar      = document.getElementById('progress-bar');
const progressCount    = document.getElementById('progress-count');
const progressLabel    = document.getElementById('progress-label-text');
const errorBox         = document.getElementById('error-box');
const disconnectedOverlay = document.getElementById('disconnected-overlay');
const btnRetry         = document.getElementById('btn-retry');

let pollTimer = null;
let savedFound = 0;   // For skipped calculation

// ── API helpers ───────────────────────────────────────────────────────────────

async function apiGet(path) {
  const res = await fetch(`${API}${path}`, { method: 'GET' });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function apiPost(path, body = {}) {
  const res = await fetch(`${API}${path}`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

// ── UI state helpers ──────────────────────────────────────────────────────────

function setStatus(text, detail = '', state = 'ready') {
  statusText.textContent   = text;
  statusDetail.textContent = detail;
  statusBar.className      = `status-bar ${state}`;
}

function setError(msg) {
  if (msg) {
    errorBox.textContent = `⚠ ${msg}`;
    errorBox.classList.add('visible');
  } else {
    errorBox.classList.remove('visible');
    errorBox.textContent = '';
  }
}

function setRunningUI(running) {
  btnStart.disabled  = running;
  btnStop.disabled   = !running;
  keywordInput.disabled  = running;
  locationInput.disabled = running;
  progressSection.classList.toggle('visible', running);
  if (!running) progressBar.style.width = '0%';
}

function updateStats(found = 0, saved = 0) {
  savedFound = found;
  statFound.textContent     = found;
  statQualified.textContent = saved;
  statSkipped.textContent   = Math.max(0, found - saved);

  if (found > 0) {
    const pct = Math.min(100, Math.round((saved / found) * 100));
    progressBar.style.width = `${pct}%`;
    progressCount.textContent = `${saved} / ${found}`;
  }
}

function setBtnLoading(btn, loading) {
  btn.classList.toggle('loading', loading);
  btn.disabled = loading;
}

// ── Backend connectivity ──────────────────────────────────────────────────────

async function checkHealth() {
  try {
    const data = await apiGet('/health');
    disconnectedOverlay.classList.remove('visible');
    const dbOk = data.database === 'connected';
    setStatus(
      dbOk ? 'Ready' : 'DB Error',
      dbOk ? 'Backend connected' : 'MySQL not connected',
      dbOk ? 'ready' : 'error'
    );
    return true;
  } catch {
    disconnectedOverlay.classList.add('visible');
    return false;
  }
}

// ── Status polling ────────────────────────────────────────────────────────────

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(pollStatus, POLL_INTERVAL_MS);
}

function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
}

async function pollStatus() {
  try {
    const data = await apiGet('/automation/status');
    const running = data.running;

    if (running) {
      setStatus('Running', `Run #${data.run_id || '?'}`, 'running');
      updateStats(data.leads_found, data.leads_saved);
      progressLabel.textContent = 'Processing leads...';
    } else {
      stopPolling();
      setRunningUI(false);

      const finalStatus = data.status || 'COMPLETED';
      if (finalStatus === 'COMPLETED') {
        setStatus('Completed', `${data.leads_saved} leads saved`, 'ready');
      } else if (finalStatus === 'STOPPED') {
        setStatus('Stopped', `Saved ${data.leads_saved} leads`, 'ready');
      } else if (finalStatus === 'FAILED') {
        setStatus('Failed', 'Check backend logs', 'error');
      }
      updateStats(data.leads_found, data.leads_saved);
    }
  } catch (err) {
    setError('Lost connection to backend.');
    stopPolling();
    setRunningUI(false);
    setStatus('Disconnected', '', 'error');
  }
}

// ── Button handlers ───────────────────────────────────────────────────────────

btnStart.addEventListener('click', async () => {
  const keyword  = keywordInput.value.trim();
  const location = locationInput.value.trim();

  if (!keyword) {
    setError('Please enter a search keyword (e.g. "web design").');
    return;
  }
  if (!location) {
    setError('Please enter a location (e.g. "United States").');
    return;
  }

  setError('');
  setBtnLoading(btnStart, true);

  try {
    await apiPost('/automation/start', { keyword, location, max_leads: 50 });
    setRunningUI(true);
    setStatus('Running', `Searching: ${keyword} in ${location}…`, 'running');
    startPolling();
  } catch (err) {
    setError(err.message);
    setStatus('Error', '', 'error');
  } finally {
    setBtnLoading(btnStart, false);
  }
});

btnStop.addEventListener('click', async () => {
  setBtnLoading(btnStop, true);
  setStatus('Stopping…', 'Finishing current page', 'stopping');
  try {
    await apiPost('/automation/stop');
  } catch (err) {
    setError(err.message);
  } finally {
    setBtnLoading(btnStop, false);
    btnStop.disabled = true;
  }
});

btnExport.addEventListener('click', async () => {
  setBtnLoading(btnExport, true);
  setError('');
  try {
    const data = await apiGet('/leads/export');
    setError('');
    setStatus('Exported!', `${data.lead_count} leads → CSV`, 'ready');
    setTimeout(() => setStatus('Ready', 'Backend connected', 'ready'), 3000);
  } catch (err) {
    setError(`Export failed: ${err.message}`);
  } finally {
    setBtnLoading(btnExport, false);
  }
});

btnRetry.addEventListener('click', async () => {
  await checkHealth();
  await pollStatus();
});

// ── Init ──────────────────────────────────────────────────────────────────────

(async () => {
  const healthy = await checkHealth();
  if (!healthy) return;

  // Restore saved search criteria
  chrome.storage.local.get(['searchKeyword', 'searchLocation'], (result) => {
    if (result.searchKeyword)  keywordInput.value  = result.searchKeyword;
    if (result.searchLocation) locationInput.value = result.searchLocation;
  });

  // Persist criteria on change
  keywordInput.addEventListener('input', () => {
    chrome.storage.local.set({ searchKeyword: keywordInput.value });
  });
  locationInput.addEventListener('input', () => {
    chrome.storage.local.set({ searchLocation: locationInput.value });
  });

  // Check if already running
  try {
    const status = await apiGet('/automation/status');
    if (status.running) {
      setRunningUI(true);
      setStatus('Running', `Run #${status.run_id}`, 'running');
      updateStats(status.leads_found, status.leads_saved);
      startPolling();
    }
  } catch {
    // Not running — that's fine
  }
})();
