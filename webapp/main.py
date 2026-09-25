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

import base64
import binascii
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Annotated, Deque, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field, StringConstraints

from bearing_tool.calc_document import build_calculation_document
from bearing_tool.catalog import Catalog, default_catalog
from bearing_tool.optimizer import find_optimal_design_for_schedule
from bearing_tool.render_html import render_calculation_document_html
from bearing_tool.render_pdf import render_calculation_document_pdf
from bearing_tool.schedule import BearingSchedule, LoadCombination

from . import config
from .emailer import Attachment, Submitter, build_email, send_email
from .extract import ALLOWED_TYPES, ExtractionError, extract_schedule

logger = logging.getLogger("assaflex.webapp")

app = FastAPI(title="AssaFlex Bearing Design Request API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_catalog: Catalog = (
    Catalog.from_json(config.CATALOG_PATH) if config.CATALOG_PATH else default_catalog()
)


# A text field the visitor must fill in (whitespace alone doesn't count).
RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


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
    # The project name -- required on the public form (it also titles the
    # engineering email and the calculation document).
    label: RequiredText
    combinations: List[LoadCombinationIn] = Field(default_factory=list)
    max_longitudinal_mm: Optional[float] = None
    max_transverse_mm: Optional[float] = None
    max_height_mm: Optional[float] = None
    mu: float = 0.3
    # None (the default) lets the optimizer search the manufacturing
    # catalog's msf_options for the smallest value that makes a feasible
    # design possible (see bearing_tool.schedule.BearingSchedule.msf) --
    # this form deliberately doesn't expose an msf field to the visitor, so
    # it's always None here in practice, letting the catalog decide.
    # le=1.0: EN 1337-3's own full stated allowance is the ceiling this tool
    # enforces everywhere (see solver.py's evaluate_bearing and
    # Catalog.msf_options) -- rejected here too (422) for a caller posting
    # directly to this API, not just the form's own UI. Per Ash: cap msf at
    # 1.0 everywhere.
    msf: Optional[float] = Field(default=None, le=1.0)
    esl: int = 0
    # The lowest vertical load this bearing could plausibly see in service
    # (kN) -- used for the Type B (friction-only) vs Type C (positive
    # fixing) check (see bearing_tool.schedule.BearingSchedule.
    # min_vertical_kN). Left blank/None, the check still runs using 0 kN --
    # the design output always says which was used, never silently skips it.
    min_vertical_kN: Optional[float] = None


class SubmitterIn(BaseModel):
    name: RequiredText
    company: RequiredText
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
    # Present when the visitor filled the form by uploading their schedule
    # (see /api/extract-schedule): the original file, attached to the
    # engineering email so the extracted values can be checked against it,
    # plus what the extraction flagged. The visitor has reviewed the values
    # in the form before submitting; this is the audit trail.
    source_file: Optional["SourceFileIn"] = None
    extraction: Optional["ExtractionInfoIn"] = None


class SourceFileIn(BaseModel):
    filename: str = Field(max_length=200)
    content_type: str
    data_base64: str


class ExtractionInfoIn(BaseModel):
    model: str = ""
    warnings: List[str] = Field(default_factory=list)
    checks: List[str] = Field(default_factory=list)


DesignRequestIn.model_rebuild()


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
    msf: Optional[float] = None
    plan_area_mm2: Optional[float] = None
    total_volume_mm3: Optional[float] = None
    feasible_count: int = 0
    combinations_evaluated: int = 0
    # What was actually used for the Type B (friction-only) vs Type C
    # (positive fixing) check -- always populated, whether or not a design
    # was found, so a blank/omitted field on the request never reads as
    # "not checked" (see ScheduleIn.min_vertical_kN).
    min_vertical_kN_used: float = 0.0
    min_vertical_assumed_zero: bool = False
    # True if the search hit SEARCH_TIME_BUDGET_S and stopped early -- any
    # design shown is then the best found so far, not a proven optimum.
    timed_out: bool = False
    # The branded "AssaFlex Calculation Document" (see bearing_tool.calc_document)
    # for the winning design, as a ready-to-embed HTML string -- only ever
    # populated on the access-code-authorized path, same gating as every
    # other field above. A PDF version of the same document is available via
    # POST /api/design-document.pdf with the same request payload.
    document_html: Optional[str] = None


class DesignRequestOut(BaseModel):
    status: str
    message: str
    design: Optional[DesignOut] = None


def _design_out(result) -> DesignOut:
    if result.best is None:
        return DesignOut(feasible=False, message=result.message,
                          feasible_count=result.feasible_count,
                          combinations_evaluated=result.combinations_evaluated,
                          min_vertical_kN_used=result.min_vertical_kN_used,
                          min_vertical_assumed_zero=result.min_vertical_assumed_zero,
                          timed_out=result.timed_out)
    b = result.best
    return DesignOut(
        feasible=True, message=result.message,
        w_mm=b.w, l_mm=b.l, h_mm=b.result.overal_height,
        total_elastomer_thickness_mm=b.n * b.ti,
        n=b.n, ti_mm=b.ti, ts_mm=b.ts, g_n_per_mm2=b.g, bearing_type=b.bearing_type,
        msf=b.msf, plan_area_mm2=b.plan_area, total_volume_mm3=b.total_volume,
        feasible_count=result.feasible_count,
        combinations_evaluated=result.combinations_evaluated,
        min_vertical_kN_used=result.best_check.min_vertical_kN_used,
        min_vertical_assumed_zero=result.best_check.min_vertical_assumed_zero,
        timed_out=result.timed_out,
    )


def _schedule_from_payload(schedule_in: ScheduleIn) -> BearingSchedule:
    return BearingSchedule(
        label=schedule_in.label,
        combinations=[LoadCombination(**c.model_dump()) for c in schedule_in.combinations],
        max_longitudinal_mm=schedule_in.max_longitudinal_mm,
        max_transverse_mm=schedule_in.max_transverse_mm,
        max_height_mm=schedule_in.max_height_mm,
        mu=schedule_in.mu, msf=schedule_in.msf, esl=schedule_in.esl,
        min_vertical_kN=schedule_in.min_vertical_kN,
    )


def _require_access_code(access_code: str) -> None:
    access_code = access_code.strip()
    if not access_code or not config.DESIGN_ACCESS_CODE or access_code != config.DESIGN_ACCESS_CODE:
        raise HTTPException(401, "Incorrect access code.")


def _decode_source_file(src: Optional[SourceFileIn]) -> Optional[Attachment]:
    if src is None:
        return None
    if src.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "The attached schedule must be a PDF, PNG or JPEG file.")
    try:
        data = base64.b64decode(src.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "The attached schedule file couldn't be read.")
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"The attached schedule is larger than {config.MAX_UPLOAD_MB} MB.")
    return Attachment(filename=src.filename or "schedule", content_type=src.content_type, data=data)


# --- Upload + AI extraction -------------------------------------------------

class ExtractionOut(BaseModel):
    project_name: Optional[str] = None
    bearing_mark: Optional[str] = None
    drawing_ref: Optional[str] = None
    max_longitudinal_mm: Optional[float] = None
    max_transverse_mm: Optional[float] = None
    max_height_mm: Optional[float] = None
    stated_min_vertical_kN: Optional[float] = None
    combinations: List[LoadCombinationIn]
    warnings: List[str]   # what the model flagged while reading the file
    checks: List[str]     # plain-code sanity checks on the values it returned
    model: str


_upload_log: Dict[str, Deque[float]] = defaultdict(deque)
_upload_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    # Railway (and most hosts) sit behind a proxy that sets X-Forwarded-For.
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_upload_rate(ip: str) -> None:
    limit = config.EXTRACTIONS_PER_IP_PER_HOUR
    if limit <= 0:
        return
    now = time.monotonic()
    with _upload_lock:
        log = _upload_log[ip]
        while log and now - log[0] > 3600:
            log.popleft()
        if len(log) >= limit:
            raise HTTPException(429, "You've uploaded several schedules in the last hour. "
                                     "Please wait a while, or enter the values by hand.")
        log.append(now)


@app.post("/api/extract-schedule", response_model=ExtractionOut)
async def extract_schedule_endpoint(
    request: Request,
    file: UploadFile = File(...),
    bearing_mark: str = Form(""),
) -> ExtractionOut:
    """Read a bearing schedule from an uploaded PDF/image and return rows to
    pre-fill the form. Nothing is designed or emailed here -- the visitor
    reviews the values and submits them through /api/design-schedule."""
    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(503, "Schedule upload isn't available right now. Please enter the values by hand.")
    content_type = (file.content_type or "").lower()
    if content_type == "image/jpg":
        content_type = "image/jpeg"
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Please upload a PDF, PNG or JPEG file.")
    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(413, f"That file is larger than {config.MAX_UPLOAD_MB} MB.")
    if not content:
        raise HTTPException(400, "That file is empty.")
    if content_type == "application/pdf" and not content.startswith(b"%PDF"):
        raise HTTPException(415, "That file doesn't look like a PDF.")
    _check_upload_rate(_client_ip(request))

    from starlette.concurrency import run_in_threadpool
    try:
        result = await run_in_threadpool(extract_schedule, content, content_type, bearing_mark)
    except ExtractionError as exc:
        raise HTTPException(422, str(exc))
    return ExtractionOut(
        project_name=result.project_name, bearing_mark=result.bearing_mark,
        drawing_ref=result.drawing_ref,
        max_longitudinal_mm=result.max_longitudinal_mm,
        max_transverse_mm=result.max_transverse_mm, max_height_mm=result.max_height_mm,
        stated_min_vertical_kN=result.stated_min_vertical_kN,
        combinations=[LoadCombinationIn(**c) for c in result.combinations],
        warnings=result.warnings, checks=result.checks, model=result.model,
    )


@app.get("/api/features")
def features() -> dict:
    """Lets the form hide the upload option when it isn't configured."""
    return {"schedule_upload": bool(config.ANTHROPIC_API_KEY), "max_upload_mb": config.MAX_UPLOAD_MB}


@app.post("/api/design-schedule", response_model=DesignRequestOut)
def design_schedule(payload: DesignRequestIn) -> DesignRequestOut:
    if not payload.schedule.combinations:
        raise HTTPException(400, "Add at least one load combination.")

    schedule = _schedule_from_payload(payload.schedule)

    access_code = payload.access_code.strip()
    if access_code:
        # Access-code path: reveal the design directly, skip the
        # engineering/sales email entirely (AssaFlex's choice -- a correct
        # code is treated as a trusted bypass, not just an alternate view).
        _require_access_code(access_code)
        result = find_optimal_design_for_schedule(
            schedule, _catalog, time_budget_s=config.SEARCH_TIME_BUDGET_S)
        design_out = _design_out(result)
        if result.best is not None:
            b = result.best
            doc = build_calculation_document(
                w=b.w, l=b.l, n=b.n, ti=b.ti, ts=b.ts, g=b.g, mu=schedule.mu,
                bearing_type=b.bearing_type, msf=b.msf, esl=schedule.esl,
                client_name=payload.submitter.company or payload.submitter.name,
                project_name=schedule.label,
            )
            design_out.document_html = render_calculation_document_html(doc)
        return DesignRequestOut(
            status="authorized",
            message="Access code accepted — showing the computed design below.",
            design=design_out,
        )

    # Normal path: compute + email engineering/sales, acknowledge only.
    result = find_optimal_design_for_schedule(
        schedule, _catalog, time_budget_s=config.SEARCH_TIME_BUDGET_S)

    submitter = Submitter(**payload.submitter.model_dump(exclude={"email"}),
                           email=str(payload.submitter.email))
    attachment = _decode_source_file(payload.source_file)
    extraction = payload.extraction.model_dump() if payload.extraction else None
    subject, html = build_email(schedule, submitter, result, extraction=extraction,
                                source_filename=attachment.filename if attachment else None)

    to_addrs = config.ENGINEERING_EMAILS + config.SALES_EMAILS
    try:
        send_email(subject, html, to_addrs,
                   attachments=[attachment] if attachment else None)
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


@app.post("/api/design-document.pdf")
def design_document_pdf(payload: DesignRequestIn) -> Response:
    """Same request shape as /api/design-schedule -- returns the winning
    design's branded calculation document as a downloadable PDF. Access-code
    gated exactly like that endpoint's "authorized" path; this is never
    reachable from the plain (email-routed) visitor flow."""
    _require_access_code(payload.access_code)
    if not payload.schedule.combinations:
        raise HTTPException(400, "Add at least one load combination.")

    schedule = _schedule_from_payload(payload.schedule)
    result = find_optimal_design_for_schedule(
        schedule, _catalog, time_budget_s=config.SEARCH_TIME_BUDGET_S)
    if result.best is None:
        raise HTTPException(404, "No feasible design found for this schedule.")

    b = result.best
    doc = build_calculation_document(
        w=b.w, l=b.l, n=b.n, ti=b.ti, ts=b.ts, g=b.g, mu=schedule.mu,
        bearing_type=b.bearing_type, msf=b.msf, esl=schedule.esl,
        client_name=payload.submitter.company or payload.submitter.name,
        project_name=schedule.label,
    )
    pdf_bytes = render_calculation_document_pdf(doc)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=assaflex_calculation_document.pdf"},
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="webapp/static"), name="static")
