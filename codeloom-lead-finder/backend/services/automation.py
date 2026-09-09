"""
backend/services/automation.py
────────────────────────────────
Playwright browser automation service.

Discovery strategy (NEW):
  1. Build a Google search query:  site:facebook.com "<keyword>" "<location>"
  2. Collect Facebook page URLs from Google search results (public, no login).
  3. Visit each discovered page with Playwright.
  4. Extract publicly visible business information.
  5. Feed each page's data to lead_discovery.process_candidate().
  6. Save QUALIFIED leads to MySQL.
  7. Continue until max_leads saved or no more candidates.

Why Google search?
  - Google returns real, indexed public Facebook business pages.
  - No Facebook login or rate-limit bypass needed.
  - Results are keyword+location specific — exactly what the goal requires.
  - Playwright can fetch and parse Google search HTML.

SCOPE:
  Only accesses publicly visible information (no login bypass,
  no CAPTCHA bypass, no private data, no rate limit circumvention).
"""
from __future__ import annotations

import asyncio
import re
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone

from playwright.async_api import async_playwright, Page, Browser

from backend.config import settings
from backend.database import get_connection
from backend.models import Lead, AutomationRun
from backend.services.lead_discovery import process_candidate
from backend.utils.logger import get_logger
from backend.utils.normalizers import normalize_facebook_url, normalize_url

logger = get_logger(__name__)

# ── Global state ──────────────────────────────────────────────────────────────

_MAX_RUN_SECONDS: int = 600   # 10-minute hard limit (multi-page discovery takes longer)

_current_run:    AutomationRun | None = None
_stop_requested: bool = False
_active_thread:  threading.Thread | None = None
_run_lock = threading.RLock()


def request_stop() -> None:
    global _stop_requested
    _stop_requested = True
    logger.info("Stop requested.")


def is_running() -> bool:
    global _current_run, _active_thread
    with _run_lock:
        if _current_run is not None and _current_run.status == "RUNNING":
            if _active_thread is not None and not _active_thread.is_alive():
                logger.warning("Automation thread is no longer alive. Marking run as FAILED.")
                _current_run.status = "FAILED"
                if not _current_run.error_msg:
                    _current_run.error_msg = "Automation thread terminated unexpectedly."
                if _current_run.id:
                    try:
                        _update_run_record(
                            _current_run.id,
                            status="FAILED",
                            error_msg=_current_run.error_msg[:500],
                            stopped_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        )
                    except Exception as db_exc:
                        logger.error("Failed to update dead thread status in DB: %s", db_exc)
                return False
            return True
        return False


def _get_latest_run_from_db() -> AutomationRun | None:
    """Fetch the latest automation_runs record from DB."""
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM automation_runs ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            run = AutomationRun(
                id=row["id"],
                started_at=row.get("started_at"),
                stopped_at=row.get("stopped_at"),
                status=row.get("status") or "FAILED",
                leads_found=row.get("leads_found") or 0,
                leads_saved=row.get("leads_saved") or 0,
                error_msg=row.get("error_msg"),
            )
            # If DB row is still marked RUNNING but server restarted / thread is dead
            if run.status == "RUNNING":
                run.status = "FAILED"
                run.error_msg = "Server restarted while automation was running."
                try:
                    _update_run_record(run.id, status="FAILED", error_msg=run.error_msg)
                except Exception:
                    pass
            return run
    except Exception as exc:
        logger.error("Failed to fetch latest run from DB: %s", exc)
    return None


def get_current_run() -> AutomationRun | None:
    global _current_run
    is_running()  # Check thread liveness & update state if needed
    if _current_run is None:
        _current_run = _get_latest_run_from_db()
    return _current_run


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


# ── Google search discovery ───────────────────────────────────────────────────

# Facebook page URL patterns we want (business pages, not user profiles/groups)
_FB_PAGE_RE = re.compile(
    r"https?://(?:www\.)?facebook\.com/(?!groups/|events/|watch/|marketplace/|pages/category/|hashtag/|login|checkpoint|story\.php|share|sharer|permalink|photo|video|reel)([a-zA-Z0-9.\-_]+)(?:/[^\s\"'?#]*)?",
    re.IGNORECASE,
)

# Noise paths to skip even if matched above
_SKIP_PATH_FRAGMENTS = [
    "/login", "/reg/", "/recover", "/checkpoint", "/help", "/privacy",
    "/terms", "/settings", "/messages", "/notifications", "/directory/",
    "/photo", "/video", "/story", "/events", "/groups", "/watch", "/reels",
]


def _is_valid_fb_page_url(url: str) -> bool:
    """Return True if url looks like a public FB business page."""
    url_lower = url.lower()
    if not _FB_PAGE_RE.search(url):
        return False
    if any(f in url_lower for f in _SKIP_PATH_FRAGMENTS):
        return False
    return True


async def _discover_via_search(
    page: Page,
    keyword: str,
    location: str,
    max_candidates: int,
) -> list[str]:
    """
    Discover public Facebook business page URLs for keyword + location.

    Strategy (tried in order):
      1. DuckDuckGo HTML search (most permissive, no JS required)
      2. Bing search (fallback)

    Both are public search engines with no API key required.
    """
    candidates = await _search_duckduckgo(page, keyword, location, max_candidates)
    if not candidates:
        logger.info("DuckDuckGo returned 0 results — trying Bing...")
        candidates = await _search_bing(page, keyword, location, max_candidates)
    return candidates


async def _parse_fb_links_from_page(page: Page, seen: set[str], max_candidates: int) -> list[str]:
    """Extract valid Facebook business page URLs from the current search result page."""
    found: list[str] = []
    try:
        link_elements = await page.query_selector_all("a[href]")
        for el in link_elements:
            href = await el.get_attribute("href") or ""

            # Bing / DDG sometimes wrap real URLs inside redirectors
            for param in ("u", "q", "url"):
                if f"/{param}=" in href or f"?{param}=" in href or f"&{param}=" in href:
                    parsed = urllib.parse.urlparse(href)
                    qs = urllib.parse.parse_qs(parsed.query)
                    candidate = qs.get(param, [""])[0]
                    if candidate and "facebook.com" in candidate.lower():
                        href = candidate
                        break

            if not href.startswith("http"):
                continue

            href = urllib.parse.unquote(href)
            if "facebook.com" not in href.lower():
                continue

            norm = normalize_facebook_url(href) or href.rstrip("/")
            if norm in seen:
                continue
            if not _is_valid_fb_page_url(norm):
                continue

            seen.add(norm)
            found.append(norm)
            logger.debug("Discovered candidate: %s", norm)

            if len(found) >= max_candidates:
                break
    except Exception as exc:
        logger.debug("Link extraction error (non-critical): %s", exc)
    return found


async def _search_duckduckgo(
    page: Page,
    keyword: str,
    location: str,
    max_candidates: int,
) -> list[str]:
    """
    Search DuckDuckGo HTML endpoint (html.duckduckgo.com) which returns
    plain HTML results without JavaScript and is very permissive with bots.
    """
    # DDG HTML endpoint: no JS, no CAPTCHA, no API key
    query = f'site:facebook.com {keyword} {location}'
    encoded = urllib.parse.urlencode({"q": query})
    ddg_url = f"https://html.duckduckgo.com/html/?{encoded}"

    candidates: list[str] = []
    seen: set[str] = set()

    try:
        logger.info("DuckDuckGo search: %s", query)
        await page.goto(ddg_url, wait_until="domcontentloaded", timeout=20_000)
        await page.wait_for_timeout(1500)

        # DDG HTML page has results in <a class="result__url"> and <a class="result__a">
        # Also check generic links
        found = await _parse_fb_links_from_page(page, seen, max_candidates)
        candidates.extend(found)

        # Try getting page 2 if needed
        if len(candidates) < max_candidates:
            try:
                next_btn = await page.query_selector('input[type="submit"][value="Next"]')
                if not next_btn:
                    next_btn = await page.query_selector('a.nav-link')
                if next_btn:
                    await next_btn.click()
                    await page.wait_for_timeout(1500)
                    found2 = await _parse_fb_links_from_page(page, seen, max_candidates - len(candidates))
                    candidates.extend(found2)
            except Exception:
                pass

    except Exception as exc:
        logger.error("DuckDuckGo search failed: %s", exc)

    logger.info("DuckDuckGo returned %d candidate URLs.", len(candidates))
    return candidates[:max_candidates]


async def _search_bing(
    page: Page,
    keyword: str,
    location: str,
    max_candidates: int,
) -> list[str]:
    """Bing search fallback."""
    query = f'site:facebook.com {keyword} {location}'
    encoded = urllib.parse.urlencode({"q": query, "count": 50})
    bing_url = f"https://www.bing.com/search?{encoded}"

    candidates: list[str] = []
    seen: set[str] = set()

    try:
        logger.info("Bing search: %s", query)
        await page.goto(bing_url, wait_until="domcontentloaded", timeout=20_000)
        await page.wait_for_timeout(2000)

        found = await _parse_fb_links_from_page(page, seen, max_candidates)
        candidates.extend(found)

        # Try page 2
        if len(candidates) < max_candidates:
            try:
                next_btn = await page.query_selector('a.sb_pagN, a[title="Next page"]')
                if next_btn:
                    await next_btn.click()
                    await page.wait_for_timeout(2000)
                    found2 = await _parse_fb_links_from_page(page, seen, max_candidates - len(candidates))
                    candidates.extend(found2)
            except Exception:
                pass

    except Exception as exc:
        logger.error("Bing search failed: %s", exc)

    logger.info("Bing returned %d candidate URLs.", len(candidates))
    return candidates[:max_candidates]


# ── Facebook page extractor ───────────────────────────────────────────────────

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
    """
    try:
        raw_title = await page.title()
        business_name = re.sub(r"\s*[\|\-–]\s*Facebook.*$", "", raw_title, flags=re.IGNORECASE).strip()
        if not business_name or business_name.lower() in ["facebook", "log in", "sign up", ""]:
            h1_text = await _safe_text(page, "h1")
            business_name = h1_text or source_name

        current_url = page.url

        # About / description text
        about_text = ""
        for sel in [
            '[data-testid="page-intro-card"]',
            'div[role="main"] div[data-key="about"]',
            'div[data-pagelet="PageInfo"]',
            'div[data-pagelet="ProfileTilesFeed_0"]',
        ]:
            about_text = await _safe_text(page, sel)
            if about_text:
                break

        # Fallback to meta description
        if not about_text:
            try:
                meta_desc = await page.get_attribute('meta[name="description"]', "content")
                about_text = meta_desc or ""
            except Exception:
                pass

        # Also grab all visible text from main content as fallback
        if not about_text:
            try:
                about_text = await _safe_text(page, 'div[role="main"]')
                about_text = about_text[:1000]
            except Exception:
                pass

        # Website field (link to external site)
        website_field = ""
        try:
            links = await page.query_selector_all('a[href]')
            for lnk in links:
                href = await lnk.get_attribute("href") or ""
                if href.startswith("http") and "facebook.com" not in href.lower():
                    # Skip social/messaging links
                    social = ["instagram.com", "twitter.com", "x.com", "youtube.com",
                              "wa.me", "t.me", "linkedin.com", "tiktok.com"]
                    if not any(s in href.lower() for s in social):
                        website_field = href
                        break
        except Exception:
            pass

        # Phone field
        phone_field = await _safe_text(page, '[aria-label*="Phone"]')
        if not phone_field:
            phone_field = await _safe_text(page, '[aria-label*="phone"]')

        # Category
        category_hint = await _safe_text(page, '[data-testid="page-category"]')
        if not category_hint:
            # Try to find category from page info section
            try:
                all_spans = await page.query_selector_all('span')
                for span in all_spans[:50]:
                    span_text = (await span.inner_text()).strip()
                    # FB categories are typically short, title-case phrases
                    if 3 < len(span_text) < 40 and span_text.istitle():
                        category_hint = span_text
                        break
            except Exception:
                pass

        # Posts
        post_text = ""
        try:
            posts = await page.query_selector_all('[data-testid="post_message"]')
            if posts:
                post_text = (await posts[0].inner_text()).strip()
        except Exception:
            pass

        return {
            "facebook_url":   current_url,
            "page_url":       current_url,
            "business_name":  business_name,
            "category_hint":  category_hint or None,
            "about_text":     about_text or None,
            "post_text":      post_text or None,
            "website_field":  website_field or None,
            "phone_field":    phone_field or None,
            "whatsapp_field": None,
            "country":        None,
            "city":           None,
            "source":         source_name,
            "source_post":    post_text[:300] if post_text else None,
        }
    except Exception as exc:
        logger.error("Error extracting page data from %s: %s", page.url, exc)
        return None


async def _check_login_or_restricted_page(page: Page) -> tuple[bool, str]:
    """Check if current page requires login or access is restricted."""
    try:
        curr_url = page.url.lower()
        if any(k in curr_url for k in ["/login", "login.php", "/checkpoint", "/recover", "/reg/"]):
            return True, "Login required to access this Facebook URL"

        title = (await page.title()).lower().strip()
        login_titles = [
            "log in to facebook",
            "log into facebook",
            "sign up for facebook",
            "facebook – log in or sign up",
            "content not found",
            "page not found",
        ]
        if any(title == lt or title.startswith(lt) for lt in login_titles):
            return True, f"Facebook page restricted or not found (Title: '{await page.title()}')"

        if title in ("facebook", ""):
            return True, "Facebook page appears restricted (generic/empty title)"

    except Exception:
        pass
    return False, ""


# ── Main automation loop ──────────────────────────────────────────────────────

async def _run_automation(keyword: str, location: str, max_leads: int, run_id: int) -> None:
    """
    Async automation loop:
      1. Google search → discover Facebook page URLs
      2. Visit each page → extract data → qualify → save
    """
    global _current_run, _stop_requested

    _stop_requested = False
    leads_found = 0
    leads_saved = 0

    source_name = f"{keyword} / {location}"

    browser: Browser | None = None
    try:
        async with async_playwright() as pw:
            logger.info("Launching Playwright Chromium (headless=%s)...", settings.automation_headless)
            browser = await pw.chromium.launch(
                headless=settings.automation_headless,
                slow_mo=settings.automation_slow_mo,
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                )
            )
            context.set_default_navigation_timeout(20_000)
            context.set_default_timeout(8_000)

            page = await context.new_page()

            # ── Step 1: Discover candidate Facebook pages via search ─────────
            logger.info("Discovering leads for keyword='%s' location='%s'", keyword, location)
            max_candidates = max(max_leads * 3, 60)   # fetch more than needed to allow for failures
            candidates = await _discover_via_search(page, keyword, location, max_candidates)

            if not candidates:
                raise RuntimeError(
                    f"Search returned 0 Facebook page candidates for "
                    f"keyword='{keyword}' location='{location}'. "
                    "Try a different keyword or check your internet connection."
                )

            logger.info("Starting processing of %d candidate pages...", len(candidates))

            # ── Step 2: Process each candidate ───────────────────────────────
            for fb_url in candidates:
                if _stop_requested:
                    logger.info("Stop requested — halting automation loop.")
                    break
                if leads_saved >= max_leads:
                    logger.info("Max leads (%d) reached.", max_leads)
                    break

                try:
                    logger.info("Visiting: %s", fb_url)
                    await page.goto(fb_url, wait_until="domcontentloaded", timeout=20_000)
                    await page.wait_for_timeout(2000)

                    is_restricted, reason = await _check_login_or_restricted_page(page)
                    if is_restricted:
                        logger.info("Skipping restricted page (%s): %s", reason, fb_url)
                        continue

                    raw_data = await _extract_page_data(page, source_name)
                    if not raw_data:
                        logger.warning("No data extracted from: %s", fb_url)
                        continue

                    leads_found += 1
                    lead, status = process_candidate(raw_data)
                    if _current_run:
                        _current_run.leads_found = leads_found

                    if status == "QUALIFIED":
                        saved_id = _save_lead(lead)
                        if saved_id:
                            leads_saved += 1
                            if _current_run:
                                _current_run.leads_saved = leads_saved

                    # Periodic DB progress save
                    if leads_found % 5 == 0:
                        _update_run_record(
                            run_id,
                            leads_found=leads_found,
                            leads_saved=leads_saved,
                        )

                    # Polite delay between page visits (respect server load)
                    await page.wait_for_timeout(1500)

                except Exception as page_exc:
                    logger.error("Error processing %s: %s — continuing.", fb_url, page_exc)
                    continue  # Never let one bad page kill the whole run

            await browser.close()
            browser = None

        final_status = "STOPPED" if _stop_requested else "COMPLETED"
        _update_run_record(
            run_id,
            status=final_status,
            stopped_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            leads_found=leads_found,
            leads_saved=leads_saved,
        )
        if _current_run:
            _current_run.status      = final_status
            _current_run.leads_found = leads_found
            _current_run.leads_saved = leads_saved
        logger.info("Automation %s. Found=%d Saved=%d", final_status, leads_found, leads_saved)

    except Exception as exc:
        logger.error("Automation run failed for run_id=%d: %s", run_id, exc, exc_info=True)
        err_str = str(exc)[:500]
        _update_run_record(
            run_id,
            status="FAILED",
            error_msg=err_str,
            stopped_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            leads_found=leads_found,
            leads_saved=leads_saved,
        )
        if _current_run:
            _current_run.status      = "FAILED"
            _current_run.error_msg   = err_str
            _current_run.leads_found = leads_found
            _current_run.leads_saved = leads_saved
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass


def start_automation(keyword: str, location: str, max_leads: int = 50) -> AutomationRun:
    """
    Start the automation in a background thread.
    Creates DB record and _current_run object synchronously.
    Returns the AutomationRun object immediately.
    Raises RuntimeError if automation is already running.
    """
    global _current_run, _active_thread
    with _run_lock:
        if is_running():
            raise RuntimeError("Automation is already running.")

        run_id = _create_run_record()
        _current_run = AutomationRun(
            id          = run_id,
            started_at  = datetime.now(timezone.utc),
            status      = "RUNNING",
            leads_found = 0,
            leads_saved = 0,
            error_msg   = None,
        )

        def _thread_target():
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    asyncio.wait_for(
                        _run_automation(keyword, location, max_leads, run_id),
                        timeout=_MAX_RUN_SECONDS,
                    )
                )
            except asyncio.TimeoutError:
                logger.error("Automation run_id=%d exceeded %ds global timeout.", run_id, _MAX_RUN_SECONDS)
                err_msg = f"Automation timed out after {_MAX_RUN_SECONDS}s"
                try:
                    _update_run_record(
                        run_id,
                        status="FAILED",
                        error_msg=err_msg,
                        stopped_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    )
                except Exception:
                    pass
                if _current_run and _current_run.status == "RUNNING":
                    _current_run.status    = "FAILED"
                    _current_run.error_msg = err_msg
            except Exception as exc:
                logger.error("Automation thread unexpected error: %s", exc)
                err_msg = str(exc)[:500]
                try:
                    _update_run_record(
                        run_id,
                        status="FAILED",
                        error_msg=err_msg,
                        stopped_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    )
                except Exception:
                    pass
                if _current_run and _current_run.status == "RUNNING":
                    _current_run.status    = "FAILED"
                    _current_run.error_msg = err_msg
            finally:
                loop.close()

        _active_thread = threading.Thread(
            target=_thread_target, daemon=True, name="automation-thread"
        )
        _active_thread.start()
        logger.info(
            "Automation background thread launched (run_id=%d, keyword='%s', location='%s').",
            run_id, keyword, location,
        )
        return _current_run


def stop_automation() -> str:
    """Request a graceful stop. Returns 'stopping' or 'not_running'."""
    if not is_running():
        return "not_running"
    request_stop()
    return "stopping"
