"""
backend/services/automation.py
────────────────────────────────
Playwright browser automation service.

Responsibilities:
  - Launch / close browser sessions
  - Navigate to public Facebook sources
  - Extract publicly available business page data
  - Feed each page data dict to the lead_discovery pipeline
  - Save qualified leads to MySQL
  - Track automation run state (START/STOP)

SCOPE:
  Only accesses publicly visible information (no login bypass,
  no CAPTCHA bypass, no private data, no rate limit circumvention).
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from typing import Callable

from playwright.async_api import async_playwright, Page, Browser, Playwright

from backend.config import settings
from backend.database import get_connection
from backend.models import Lead, AutomationRun
from backend.services.lead_discovery import process_candidate
from backend.utils.logger import get_logger
from backend.utils.normalizers import normalize_facebook_url

logger = get_logger(__name__)

# ── Global state ──────────────────────────────────────────────────────────────

_current_run:    AutomationRun | None = None
_stop_requested: bool = False
_run_lock = threading.Lock()


def get_current_run() -> AutomationRun | None:
    return _current_run


def request_stop() -> None:
    global _stop_requested
    _stop_requested = True
    logger.info("Stop requested.")


def is_running() -> bool:
    return _current_run is not None and _current_run.status == "RUNNING"


# ── Database helpers ──────────────────────────────────────────────────────────

def _create_run_record() -> int:
    """Insert a new automation_runs row and return its id."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO automation_runs (status) VALUES ('RUNNING')"
        )
        conn.commit()
        run_id = cursor.lastrowid
        cursor.close()
        return run_id
    finally:
        conn.close()


def _update_run_record(run_id: int, **fields) -> None:
    """Update an automation_runs row with provided fields."""
    if not fields:
        return
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE automation_runs SET {set_clause} WHERE id = %s",
            (*fields.values(), run_id),
        )
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def _save_lead(lead: Lead) -> int | None:
    """Insert a Lead into the database. Returns the new row id."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO leads (
                business_name, category, facebook_url, page_url,
                country, city, website, website_status,
                business_phone, business_whatsapp,
                source, source_post,
                lead_score, lead_priority, status
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s
            )
            """,
            (
                lead.business_name, lead.category, lead.facebook_url, lead.page_url,
                lead.country, lead.city, lead.website, lead.website_status,
                lead.business_phone, lead.business_whatsapp,
                lead.source, lead.source_post,
                lead.lead_score, lead.lead_priority, lead.status,
            ),
        )
        conn.commit()
        lead_id = cursor.lastrowid
        cursor.close()
        logger.info("Lead saved: id=%d name=%s", lead_id, lead.business_name)
        return lead_id
    except Exception as exc:
        logger.error("Failed to save lead '%s': %s", lead.business_name, exc)
        conn.rollback()
        return None
    finally:
        conn.close()


# ── Playwright page extractors ────────────────────────────────────────────────

async def _safe_text(page: Page, selector: str) -> str:
    """Return inner text of selector or empty string on failure."""
    try:
        el = await page.query_selector(selector)
        if el:
            return (await el.inner_text()).strip()
    except Exception:
        pass
    return ""


async def _extract_page_data(page: Page, source_name: str) -> dict | None:
    """
    Extract publicly available data from a Facebook business page.
    Returns a raw data dict for lead_discovery.process_candidate(), or None on error.

    NOTE: Only reads publicly displayed content — no login bypass, no private data.
    """
    try:
        # Page name / title
        business_name = await page.title()
        business_name = business_name.replace(" | Facebook", "").strip()

        # Current URL (normalized)
        current_url = page.url

        # About section — publicly visible on business pages
        about_text = await _safe_text(page, '[data-testid="page-intro-card"]')
        if not about_text:
            about_text = await _safe_text(page, "div[role='main'] div[data-key='about']")

        # Website field if displayed
        website_field = await _safe_text(page, 'a[role="link"][href^="http"]:not([href*="facebook.com"])')

        # Phone field if displayed publicly
        phone_field = await _safe_text(page, '[aria-label*="Phone"]')

        # Category
        category_hint = await _safe_text(page, '[data-testid="page-category"]')

        # Most recent visible post text (first post)
        post_text = ""
        posts = await page.query_selector_all('[data-testid="post_message"]')
        if posts:
            post_text = (await posts[0].inner_text()).strip()

        return {
            "facebook_url":  current_url,
            "page_url":      current_url,
            "business_name": business_name,
            "category_hint": category_hint or None,
            "about_text":    about_text or None,
            "post_text":     post_text or None,
            "website_field": website_field or None,
            "phone_field":   phone_field or None,
            "whatsapp_field": None,
            "country":       None,   # Can be enriched later
            "city":          None,
            "source":        source_name,
            "source_post":   post_text[:300] if post_text else None,
        }
    except Exception as exc:
        logger.error("Error extracting page data: %s", exc)
        return None


# ── Main automation loop ──────────────────────────────────────────────────────

async def _run_automation(source_url: str, max_leads: int) -> None:
    """Async automation loop — runs in its own event loop thread."""
    global _current_run, _stop_requested

    run_id = _create_run_record()
    _current_run = AutomationRun(
        id         = run_id,
        started_at = datetime.now(timezone.utc),
        status     = "RUNNING",
    )
    _stop_requested = False

    leads_found = 0
    leads_saved = 0

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless  = settings.automation_headless,
            slow_mo   = settings.automation_slow_mo,
        )
        context = await browser.new_context()
        page    = await context.new_page()

        try:
            logger.info("Navigating to source: %s", source_url)
            await page.goto(source_url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(2000)

            source_name = source_url.split("facebook.com/")[-1].split("/")[0] or "unknown"

            # ── Collect page links from the source ────────────────────────────
            # This is a simplified example: collect all internal Facebook page links.
            # A real implementation should be tuned to the specific source layout.
            page_links: list[str] = []
            links = await page.query_selector_all('a[href*="facebook.com"]')
            for link in links:
                href = await link.get_attribute("href")
                if href and "/groups/" not in href and "?" not in href:
                    norm = normalize_facebook_url(href)
                    if norm and norm not in page_links:
                        page_links.append(norm)
                if len(page_links) >= max_leads * 2:  # Collect extra to account for skips
                    break

            logger.info("Found %d candidate page links.", len(page_links))

            for link in page_links:
                if _stop_requested:
                    logger.info("Stop requested — halting automation loop.")
                    break
                if leads_saved >= max_leads:
                    logger.info("Max leads (%d) reached.", max_leads)
                    break

                try:
                    logger.info("Processing: %s", link)
                    await page.goto(link, wait_until="domcontentloaded", timeout=20_000)
                    await page.wait_for_timeout(1500)  # Polite wait

                    raw_data = await _extract_page_data(page, source_name)
                    if not raw_data:
                        continue

                    leads_found += 1
                    lead, status = process_candidate(raw_data)
                    _current_run.leads_found = leads_found

                    if status == "QUALIFIED":
                        saved_id = _save_lead(lead)
                        if saved_id:
                            leads_saved += 1
                            _current_run.leads_saved = leads_saved

                    # Update run counter in DB every 5 leads
                    if leads_found % 5 == 0:
                        _update_run_record(
                            run_id,
                            leads_found=leads_found,
                            leads_saved=leads_saved,
                        )

                except Exception as exc:
                    logger.error("Error processing link %s: %s", link, exc)
                    continue  # Never crash the whole run for one bad lead

        except Exception as exc:
            logger.error("Automation run error: %s", exc, exc_info=True)
            _update_run_record(
                run_id,
                status    = "FAILED",
                error_msg = str(exc)[:500],
                stopped_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                leads_found = leads_found,
                leads_saved = leads_saved,
            )
            _current_run.status = "FAILED"
            return
        finally:
            await browser.close()

    final_status = "STOPPED" if _stop_requested else "COMPLETED"
    _update_run_record(
        run_id,
        status     = final_status,
        stopped_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        leads_found = leads_found,
        leads_saved = leads_saved,
    )
    _current_run.status     = final_status
    _current_run.leads_found = leads_found
    _current_run.leads_saved = leads_saved
    logger.info("Automation %s. Found=%d Saved=%d", final_status, leads_found, leads_saved)


def start_automation(source_url: str, max_leads: int = 50) -> AutomationRun:
    """
    Start the automation in a background thread.
    Returns the AutomationRun object immediately.
    Raises RuntimeError if automation is already running.
    """
    global _current_run
    with _run_lock:
        if is_running():
            raise RuntimeError("Automation is already running.")

    def _thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_automation(source_url, max_leads))
        finally:
            loop.close()

    thread = threading.Thread(target=_thread_target, daemon=True, name="automation-thread")
    thread.start()
    logger.info("Automation thread started.")
    return _current_run


def stop_automation() -> str:
    """Request a graceful stop. Returns 'stopping' or 'not_running'."""
    if not is_running():
        return "not_running"
    request_stop()
    return "stopping"
