/**
 * content.js — Codeloom Lead Finder Content Script
 *
 * Injected into pages matched in manifest.json.
 * In this MVP, the content script is minimal — the actual page extraction
 * is handled server-side by Playwright (backend/services/automation.py).
 *
 * This script is reserved for future use (e.g., highlighting scraped elements,
 * user-triggered extraction from the currently open tab).
 *
 * SCOPE: Only reads publicly visible page content — no private data access.
 */

'use strict';

// Do nothing on inject unless triggered via message from background
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'PING') {
    sendResponse({ pong: true, url: window.location.href });
  }
});
