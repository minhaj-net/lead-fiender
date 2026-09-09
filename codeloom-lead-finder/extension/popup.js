/**
 * popup.js — Codeloom Lead Finder Extension
 *
 * Flow:
 *   1. On open → health check → show status
 *   2. START → POST /automation/start {keyword, location, max_leads} → poll status
 *   3. STOP  → POST /automation/stop
 *   4. DOWNLOAD CSV → GET /leads/download → fetch blob → chrome.downloads.download()
 */

'use strict';

const API             = 'http://127.0.0.1:8000';
const POLL_INTERVAL_MS = 2500;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const statusBar           = document.getElementById('status-bar');
const statusText          = document.getElementById('status-text');
const statusDetail        = document.getElementById('status-detail');
const statFound           = document.getElementById('stat-found');
const statQualified       = document.getElementById('stat-qualified');
const statSkipped         = document.getElementById('stat-skipped');
const keywordInput        = document.getElementById('search-keyword');
const locationInput       = document.getElementById('search-location');
const maxLeadsInput       = document.getElementById('max-leads');
const btnStart            = document.getElementById('btn-start');
const btnStop             = document.getElementById('btn-stop');
const btnDownload         = document.getElementById('btn-download');
const progressSection     = document.getElementById('progress-section');
const progressBar         = document.getElementById('progress-bar');
const progressCount       = document.getElementById('progress-count');
const progressLabel       = document.getElementById('progress-label-text');
const errorBox            = document.getElementById('error-box');
const disconnectedOverlay = document.getElementById('disconnected-overlay');
const btnRetry            = document.getElementById('btn-retry');

let pollTimer = null;

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

// ── UI helpers ────────────────────────────────────────────────────────────────

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
  btnStart.disabled        = running;
  btnStop.disabled         = !running;
  btnDownload.disabled     = running;          // disable during run
  keywordInput.disabled    = running;
  locationInput.disabled   = running;
  maxLeadsInput.disabled   = running;
  progressSection.classList.toggle('visible', running);
  if (!running) progressBar.style.width = '0%';
}

function updateStats(found = 0, saved = 0) {
  statFound.textContent     = found;
  statQualified.textContent = saved;
  statSkipped.textContent   = Math.max(0, found - saved);

  if (found > 0) {
    const pct = Math.min(100, Math.round((saved / found) * 100));
    progressBar.style.width   = `${pct}%`;
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
    const data   = await apiGet('/automation/status');
    const running = data.running;

    if (running) {
      setStatus('Running', `Run #${data.run_id || '?'}`, 'running');
      updateStats(data.leads_found, data.leads_saved);
      progressLabel.textContent = 'Processing leads…';
    } else {
      stopPolling();
      setRunningUI(false);

      const finalStatus = data.status || 'COMPLETED';
      if (finalStatus === 'COMPLETED') {
        setStatus('Completed', `${data.leads_saved} leads saved — ready to download`, 'ready');
      } else if (finalStatus === 'STOPPED') {
        setStatus('Stopped', `Saved ${data.leads_saved} leads`, 'ready');
      } else if (finalStatus === 'FAILED') {
        setStatus('Failed', data.error_msg || 'Check backend logs', 'error');
        if (data.error_msg) setError(data.error_msg);
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

// ── START ─────────────────────────────────────────────────────────────────────

btnStart.addEventListener('click', async () => {
  const keyword  = keywordInput.value.trim();
  const location = locationInput.value.trim();
  const maxLeads = parseInt(maxLeadsInput.value, 10);

  if (!keyword) {
    setError('Please enter a keyword (e.g. "restaurant").');
    return;
  }
  if (!location) {
    setError('Please enter a location (e.g. "Dhaka").');
    return;
  }
  if (!maxLeads || maxLeads < 1 || maxLeads > 500) {
    setError('Max Leads must be between 1 and 500.');
    return;
  }

  setError('');
  setBtnLoading(btnStart, true);

  try {
    await apiPost('/automation/start', {
      keyword,
      location,
      max_leads: maxLeads,
    });
    setRunningUI(true);
    setStatus('Running', `"${keyword}" in ${location} — up to ${maxLeads} leads`, 'running');
    updateStats(0, 0);
    startPolling();
  } catch (err) {
    setError(err.message);
    setStatus('Error', '', 'error');
  } finally {
    setBtnLoading(btnStart, false);
  }
});

// ── STOP ──────────────────────────────────────────────────────────────────────

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

// ── DOWNLOAD CSV ──────────────────────────────────────────────────────────────
//
// Flow:
//   1. fetch() GET /leads/download  →  response is a CSV file stream
//   2. Convert response to Blob
//   3. Create a temporary object URL for the Blob
//   4. chrome.downloads.download() saves it to the user's Downloads folder
//      with the correct filename from Content-Disposition
//   5. Revoke the object URL

btnDownload.addEventListener('click', async () => {
  setError('');
  setBtnLoading(btnDownload, true);

  try {
    const res = await fetch(`${API}/leads/download`, { method: 'GET' });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }

    // Extract filename from Content-Disposition header if present,
    // otherwise fall back to a dated default.
    let filename = `Codeloom_Leads_${new Date().toISOString().slice(0, 10)}.csv`;
    const cd = res.headers.get('Content-Disposition') || '';
    const fnMatch = cd.match(/filename="?([^";\n]+)"?/i);
    if (fnMatch && fnMatch[1]) filename = fnMatch[1].trim();

    // Read response as ArrayBuffer and create a Blob
    const arrayBuffer = await res.arrayBuffer();
    const blob        = new Blob([arrayBuffer], { type: 'text/csv;charset=utf-8-sig;' });
    const objectUrl   = URL.createObjectURL(blob);

    // Trigger download via chrome.downloads API
    chrome.downloads.download(
      { url: objectUrl, filename, saveAs: false },
      (downloadId) => {
        // Revoke the object URL once the download has started
        URL.revokeObjectURL(objectUrl);
        if (chrome.runtime.lastError) {
          setError(`Download failed: ${chrome.runtime.lastError.message}`);
        } else {
          setStatus('Downloaded!', `${filename}`, 'ready');
          setTimeout(() => setStatus('Ready', 'Backend connected', 'ready'), 4000);
        }
      }
    );

  } catch (err) {
    setError(`Download failed: ${err.message}`);
  } finally {
    setBtnLoading(btnDownload, false);
  }
});

// ── RETRY ─────────────────────────────────────────────────────────────────────

btnRetry.addEventListener('click', async () => {
  await checkHealth();
  await pollStatus();
});

// ── INIT ──────────────────────────────────────────────────────────────────────

(async () => {
  const healthy = await checkHealth();
  if (!healthy) return;

  // Restore saved search criteria from chrome.storage
  chrome.storage.local.get(['searchKeyword', 'searchLocation', 'maxLeads'], (result) => {
    if (result.searchKeyword)  keywordInput.value  = result.searchKeyword;
    if (result.searchLocation) locationInput.value = result.searchLocation;
    if (result.maxLeads)       maxLeadsInput.value = result.maxLeads;
  });

  // Persist on change
  keywordInput.addEventListener('input', () =>
    chrome.storage.local.set({ searchKeyword: keywordInput.value }));
  locationInput.addEventListener('input', () =>
    chrome.storage.local.set({ searchLocation: locationInput.value }));
  maxLeadsInput.addEventListener('input', () =>
    chrome.storage.local.set({ maxLeads: maxLeadsInput.value }));

  // Re-attach to a run that was already started before the popup was opened
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
