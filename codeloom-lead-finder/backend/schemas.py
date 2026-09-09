"""
backend/schemas.py
───────────────────
Pydantic models for FastAPI request bodies and response payloads.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


# ── Shared enums (as Literals for Pydantic v2 clarity) ───────────────────────

WebsiteStatus = Literal["YES", "NO", "UNCERTAIN"]
LeadPriority  = Literal["HOT", "GOOD", "MEDIUM", "LOW"]
LeadStatus    = Literal["QUALIFIED", "SKIPPED", "DUPLICATE", "UNCERTAIN", "FAILED"]
AutomationRunStatus = Literal["RUNNING", "STOPPED", "COMPLETED", "FAILED"]


# ── Lead schemas ──────────────────────────────────────────────────────────────

class LeadBase(BaseModel):
    business_name:     str | None = None
    category:          str | None = None
    facebook_url:      str | None = None
    page_url:          str | None = None
    country:           str | None = None
    city:              str | None = None
    website:           str | None = None
    website_status:    WebsiteStatus = "UNCERTAIN"
    business_phone:    str | None = None
    business_whatsapp: str | None = None
    business_email:    str | None = None
    source:            str | None = None
    source_post:       str | None = None
    lead_score:        int = Field(default=0, ge=0, le=100)
    lead_priority:     LeadPriority = "LOW"
    status:            LeadStatus = "QUALIFIED"


class LeadCreate(LeadBase):
    """Used when inserting a new lead."""
    pass


class LeadRead(LeadBase):
    """Returned when reading a lead from the DB."""
    id:         int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadUpdate(BaseModel):
    """Partial update — all fields optional."""
    business_name:     str | None = None
    category:          str | None = None
    website_status:    WebsiteStatus | None = None
    business_phone:    str | None = None
    business_whatsapp: str | None = None
    lead_score:        int | None = Field(default=None, ge=0, le=100)
    lead_priority:     LeadPriority | None = None
    status:            LeadStatus | None = None


# ── Automation schemas ────────────────────────────────────────────────────────

class AutomationStartRequest(BaseModel):
    keyword:  str = Field(..., min_length=2, description="Search keyword, e.g. 'web design'")
    location: str = Field(..., min_length=2, description="Target location, e.g. 'United States'")
    max_leads: int = Field(50, ge=1, le=500, description="Maximum leads to collect this run")


class AutomationStatusResponse(BaseModel):
    running:     bool
    run_id:      int | None = None
    started_at:  datetime | None = None
    leads_found: int = 0
    leads_saved: int = 0
    status:      AutomationRunStatus | None = None
    error_msg:   str | None = None
    message:     str = ""


# ── Health check schema ───────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status:   str = "ok"
    database: str = "unknown"
    version:  str = "1.0.0"


# ── CSV export schema ─────────────────────────────────────────────────────────

class ExportResponse(BaseModel):
    file_path:   str
    lead_count:  int
    exported_at: datetime
