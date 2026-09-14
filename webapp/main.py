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
    # Optional shared access code (see config.DESIGN_ACCESS_CODE). Left blank
    # (the default), the request goes through the normal engineering/sales
    # review flow below -- it's only ever treated as an access-code attempt
    # when non-blank, so an unconfigured DESIGN_ACCESS_CODE can't accidentally
    # be "matched" by an empty string.
    access_code: str = ""


class DesignOut(BaseModel):
    """The computed design, returned only when a correct access code is
    supplied -- never part of the normal (email-routed) response, since the
    whole point of that path is that the visitor doesn't see the numbers."""
    feasible: bool
    message: str
    w_mm: Optional[float] = None
    l_mm: Optional[float] = None
    h_mm: Optional[float] = None
    total_elastomer_thickness_mm: Optional[float] = None
    n: Optional[int] = None
    ti_mm: Optional[float] = None
    ts_mm: Optional[float] = None
    g_n_per_mm2: Optional[float] = None
    bearing_type: Optional[float] = None
    plan_area_mm2: Optional[float] = None
    total_volume_mm3: Optional[float] = None
    feasible_count: int = 0
    combinations_evaluated: int = 0


class DesignRequestOut(BaseModel):
    status: str
    message: str
    design: Optional[DesignOut] = None


def _design_out(result) -> DesignOut:
    if result.best is None:
        return DesignOut(feasible=False, message=result.message,
                          feasible_count=result.feasible_count,
                          combinations_evaluated=result.combinations_evaluated)
    b = result.best
    return DesignOut(
        feasible=True, message=result.message,
        w_mm=b.w, l_mm=b.l, h_mm=b.result.overal_height,
        total_elastomer_thickness_mm=b.n * b.ti,
        n=b.n, ti_mm=b.ti, ts_mm=b.ts, g_n_per_mm2=b.g, bearing_type=b.bearing_type,
        plan_area_mm2=b.plan_area, total_volume_mm3=b.total_volume,
        feasible_count=result.feasible_count,
        combinations_evaluated=result.combinations_evaluated,
    )


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

    access_code = payload.access_code.strip()
    if access_code:
        # Access-code path: reveal the design directly, skip the
        # engineering/sales email entirely (AssaFlex's choice -- a correct
        # code is treated as a trusted bypass, not just an alternate view).
        if not config.DESIGN_ACCESS_CODE or access_code != config.DESIGN_ACCESS_CODE:
            raise HTTPException(401, "Incorrect access code.")
        result = find_optimal_design_for_schedule(schedule, _catalog)
        return DesignRequestOut(
            status="authorized",
            message="Access code accepted — showing the computed design below.",
            design=_design_out(result),
        )

    # Normal path: compute + email engineering/sales, acknowledge only.
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


from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="webapp/static"), name="static")
