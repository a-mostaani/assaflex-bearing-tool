"""
Public-facing bearing-design-request API.

Meant to sit behind the form in ``webapp/static/design-request-form.html``
(embedded on assaflex.com — see ``webapp/README.md``). A visitor fills in
their bearing schedule, submits it here, the optimizer computes a
preliminary design, and an internal notification email goes to engineering
and sales -- the visitor only ever sees a plain acknowledgement, never the
computed numbers, since the design is explicitly preliminary pending
engineering review (AssaFlex's own choice -- see the project build log).

Run locally with:
    uvicorn webapp.main:app --reload --port 8000

See webapp/README.md for deployment and WordPress embedding instructions.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from bearing_tool.catalog import Catalog, default_catalog
from bearing_tool.optimizer import find_optimal_design_for_schedule
from bearing_tool.schedule import BearingSchedule, LoadCombination

from . import config
from .emailer import Submitter, build_email, send_email

logger = logging.getLogger("assaflex.webapp")

app = FastAPI(title="AssaFlex Bearing Design Request API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["POST"],
    allow_headers=["*"],
)

_catalog: Catalog = (
    Catalog.from_json(config.CATALOG_PATH) if config.CATALOG_PATH else default_catalog()
)


class LoadCombinationIn(BaseModel):
    limit_state: str
    case: str
    vertical_kN: float
    transverse_kN: float = 0.0
    longitudinal_kN: float = 0.0
    long_displacement_mm: float = 0.0
    trans_displacement_mm: float = 0.0
    rotation_mrad: float = 0.0
    transverse_rotation_mrad: float = 0.0


class ScheduleIn(BaseModel):
    label: str = ""
    combinations: List[LoadCombinationIn] = Field(default_factory=list)
    max_longitudinal_mm: Optional[float] = None
    max_transverse_mm: Optional[float] = None
    max_height_mm: Optional[float] = None
    mu: float = 0.3
    msf: float = 0.7
    esl: int = 0


class SubmitterIn(BaseModel):
    name: str
    company: str = ""
    email: EmailStr
    phone: str = ""
    notes: str = ""


class DesignRequestIn(BaseModel):
    schedule: ScheduleIn
    submitter: SubmitterIn


class DesignRequestOut(BaseModel):
    status: str
    message: str


@app.post("/api/design-schedule", response_model=DesignRequestOut)
def design_schedule(payload: DesignRequestIn) -> DesignRequestOut:
    if not payload.schedule.combinations:
        raise HTTPException(400, "Add at least one load combination.")

    schedule = BearingSchedule(
        label=payload.schedule.label,
        combinations=[LoadCombination(**c.model_dump()) for c in payload.schedule.combinations],
        max_longitudinal_mm=payload.schedule.max_longitudinal_mm,
        max_transverse_mm=payload.schedule.max_transverse_mm,
        max_height_mm=payload.schedule.max_height_mm,
        mu=payload.schedule.mu, msf=payload.schedule.msf, esl=payload.schedule.esl,
    )

    result = find_optimal_design_for_schedule(schedule, _catalog)

    submitter = Submitter(**payload.submitter.model_dump(exclude={"email"}),
                           email=str(payload.submitter.email))
    subject, html = build_email(schedule, submitter, result)

    to_addrs = config.ENGINEERING_EMAILS + config.SALES_EMAILS
    try:
        send_email(subject, html, to_addrs)
    except Exception:  # noqa: BLE001 -- never fail the visitor's request over email delivery
        logger.exception("Failed to send design-request notification email")
        return DesignRequestOut(
            status="received_email_failed",
            message="Your request was received, but our notification email "
                    "could not be sent. Please contact AssaFlex directly to confirm receipt.",
        )

    return DesignRequestOut(
        status="received",
        message="Thanks — your bearing schedule has been received. Our engineering "
                "team will review it and get back to you.",
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# Uncomment to have this backend also serve the form page itself (useful if
# your WordPress setup embeds it via <iframe> instead of a Custom HTML
# block -- see webapp/README.md):
#
# from fastapi.staticfiles import StaticFiles
# app.mount("/static", StaticFiles(directory="webapp/static"), name="static")
