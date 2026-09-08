/**
 * background.js — Codeloom Lead Finder Service Worker
 *
 * Handles messages from the popup and maintains persistent state
 * across popup open/close cycles via chrome.storage.
 *
 * Note: In Manifest V3, service workers are non-persistent.
 * We use chrome.storage.local for state that must survive popup close.
 */

'use strict';

const API_BASE = 'http://127.0.0.1:8000';

// ── Message handler ───────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'CHECK_HEALTH') {
    fetch(`${API_BASE}/health`)
      .then(r => r.json())
      .then(data => sendResponse({ ok: true, data }))
      .catch(() => sendResponse({ ok: false }));
    return true; // Keep channel open for async response
  }

  if (message.type === 'GET_STATUS') {
    fetch(`${API_BASE}/automation/status`)
      .then(r => r.json())
      .then(data => sendResponse({ ok: true, data }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }
});

// ── Install handler ───────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  console.log('[Codeloom] Extension installed / updated.');
  chrome.storage.local.set({ installedAt: new Date().toISOString() });
});
