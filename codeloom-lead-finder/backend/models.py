"""
backend/models.py
──────────────────
Plain dataclass representations of database rows.
These are used to pass data between service layers without coupling to
the HTTP schema layer (schemas.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


WebsiteStatus = Literal["YES", "NO", "UNCERTAIN"]
LeadPriority  = Literal["HOT", "GOOD", "MEDIUM", "LOW"]
LeadStatus    = Literal["QUALIFIED", "SKIPPED", "DUPLICATE", "UNCERTAIN", "FAILED"]


@dataclass
class Lead:
    """Represents one row in the `leads` table."""
    id:                int | None = None
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
    lead_score:        int = 0
    lead_priority:     LeadPriority = "LOW"
    status:            LeadStatus = "QUALIFIED"
    created_at:        datetime | None = None
    updated_at:        datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id":                self.id,
            "business_name":     self.business_name,
            "category":          self.category,
            "facebook_url":      self.facebook_url,
            "page_url":          self.page_url,
            "country":           self.country,
            "city":              self.city,
            "website":           self.website,
            "website_status":    self.website_status,
            "business_phone":    self.business_phone,
            "business_whatsapp": self.business_whatsapp,
            "business_email":    self.business_email,
            "source":            self.source,
            "source_post":       self.source_post,
            "lead_score":        self.lead_score,
            "lead_priority":     self.lead_priority,
            "status":            self.status,
            "created_at":        self.created_at,
            "updated_at":        self.updated_at,
        }


@dataclass
class AutomationRun:
    """Represents one row in the `automation_runs` table."""
    id:          int | None = None
    started_at:  datetime | None = None
    stopped_at:  datetime | None = None
    status:      str = "RUNNING"
    leads_found: int = 0
    leads_saved: int = 0
    error_msg:   str | None = None
