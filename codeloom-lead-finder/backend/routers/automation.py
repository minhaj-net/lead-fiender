"""
backend/routers/automation.py
──────────────────────────────
Automation control endpoints:

  POST /automation/start   — start a new automation run
  POST /automation/stop    — request graceful stop
  GET  /automation/status  — current run state
"""
from fastapi import APIRouter, HTTPException

from backend.schemas import AutomationStartRequest, AutomationStatusResponse
from backend.services import automation as auto_svc
from backend.utils.logger import get_logger

router = APIRouter(prefix="/automation", tags=["automation"])
logger = get_logger(__name__)


@router.post(
    "/start",
    response_model=AutomationStatusResponse,
    summary="Start lead-discovery automation",
)
def start_automation(request: AutomationStartRequest) -> AutomationStatusResponse:
    """
    Start the Playwright automation using keyword + location discovery.
    Returns 409 if automation is already running.
    """
    if auto_svc.is_running():
        raise HTTPException(status_code=409, detail="Automation is already running.")

    try:
        run = auto_svc.start_automation(
            keyword   = request.keyword,
            location  = request.location,
            max_leads = request.max_leads,
        )
        return AutomationStatusResponse(
            running    = True,
            run_id     = run.id if run else None,
            started_at = run.started_at if run else None,
            status     = "RUNNING",
            message    = f"Automation started: '{request.keyword}' in '{request.location}'.",
        )
    except Exception as exc:
        logger.error("Failed to start automation: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/stop",
    response_model=AutomationStatusResponse,
    summary="Stop running automation",
)
def stop_automation() -> AutomationStatusResponse:
    """
    Request a graceful stop of the current automation run.
    Returns 400 if no automation is running.
    """
    result = auto_svc.stop_automation()
    if result == "not_running":
        raise HTTPException(status_code=400, detail="No automation is currently running.")

    run = auto_svc.get_current_run()
    return AutomationStatusResponse(
        running    = False,
        run_id     = run.id if run else None,
        status     = "STOPPED",
        leads_found = run.leads_found if run else 0,
        leads_saved = run.leads_saved if run else 0,
        message    = "Stop requested. Finishing current page...",
    )


@router.get(
    "/status",
    response_model=AutomationStatusResponse,
    summary="Get current automation status",
)
def get_status() -> AutomationStatusResponse:
    """Returns the current automation run state."""
    run = auto_svc.get_current_run()
    if run is None:
        return AutomationStatusResponse(
            running = False,
            message = "No automation run yet.",
        )
    return AutomationStatusResponse(
        running     = auto_svc.is_running(),
        run_id      = run.id,
        started_at  = run.started_at,
        leads_found = run.leads_found,
        leads_saved = run.leads_saved,
        status      = run.status,
        error_msg   = run.error_msg,
        message     = f"Run {run.id} — {run.status}" + (f": {run.error_msg}" if run.error_msg else ""),
    )
