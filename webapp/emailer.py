"""
Composes and sends the "new bearing design request" notification email that
goes to engineering + sales whenever the public website form is submitted.

Deliberately does NOT send anything back to the person who filled in the
form beyond a plain "we received your request" acknowledgement (see
``main.py``) -- the computed design is explicitly preliminary, pending an
engineer's review, per AssaFlex's own choice (see the main README / project
build log). Only internal recipients see the numbers.
"""

from __future__ import annotations

import html as _html
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import List, Optional

from bearing_tool.optimizer import ScheduleOptimizationResult
from bearing_tool.schedule import BearingSchedule

from . import config


@dataclass
class Submitter:
    name: str
    company: str
    email: str
    phone: str = ""
    notes: str = ""


@dataclass
class Attachment:
    filename: str
    content_type: str
    data: bytes


def _esc(text: Optional[str]) -> str:
    """Visitor-typed text goes into an HTML email -- escape it."""
    return _html.escape(text or "")


def _fmt(value: Optional[float], unit: str = "", digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}{unit}"


def build_email(schedule: BearingSchedule, submitter: Submitter,
                 result: ScheduleOptimizationResult,
                 extraction: Optional[dict] = None,
                 source_filename: Optional[str] = None) -> tuple[str, str]:
    """Returns (subject, html_body).

    `extraction` (model/warnings/checks) and `source_filename` are set when
    the visitor filled the form by uploading their schedule -- the email then
    says so prominently, lists what was flagged, and (via send_email's
    attachments) carries the original file so the values can be checked.
    """
    raw_label = schedule.label or "(no project name given)"
    label = _esc(raw_label)
    subject = f"[PRELIMINARY] Bearing design request — {submitter.company or submitter.name} — {raw_label}"

    extraction_html = ""
    if extraction is not None:
        flagged = [*extraction.get("warnings", []), *extraction.get("checks", [])]
        flagged_html = ("<ul>" + "".join(f"<li>{_esc(w)}</li>" for w in flagged) + "</ul>"
                        if flagged else "<p>Nothing was flagged.</p>")
        extraction_html = f"""
    <div style="border-left:4px solid #b00020; padding:8px 12px; background:#fff5f5;">
      <p><strong>Schedule values were read from an uploaded file by AI</strong>
      ({_esc(extraction.get('model'))}) and then reviewed and submitted by the
      visitor. Check them against the attached original
      {('(<em>' + _esc(source_filename) + '</em>)') if source_filename else ''}
      before relying on this design.</p>
      <p>Flagged while reading the file:</p>
      {flagged_html}
    </div>"""

    rows_html = "".join(
        f"<tr><td>{c.limit_state}</td><td>{c.case}</td>"
        f"<td>{_fmt(c.vertical_kN)}</td><td>{_fmt(c.transverse_kN)}</td>"
        f"<td>{_fmt(c.longitudinal_kN)}</td>"
        f"<td>{_fmt(c.long_displacement_mm)}</td><td>{_fmt(c.trans_displacement_mm)}</td>"
        f"<td>{_fmt(c.rotation_mrad, digits=2)}</td>"
        f"<td>{_fmt(c.transverse_rotation_mrad, digits=2)}</td></tr>"
        for c in schedule.combinations
    )

    if result.best is None:
        result_html = (
            f"<p style='color:#b00020'><strong>No feasible design found</strong> "
            f"in the current manufacturing catalog for this schedule.</p>"
            f"<p>{result.message}</p>"
        )
    else:
        b = result.best
        total_ti = b.n * b.ti
        checks_html = "".join(
            f"<tr><td>{c.combination.label}</td>"
            f"<td>{'PASS' if c.passed else 'FAIL'}</td>"
            f"<td>{_fmt(c.result.total_strain_i, digits=3)}</td>"
            f"<td>{_fmt(c.result.total_strain_o, digits=3)}</td></tr>"
            for c in result.best_check.checks
        ) if result.best_check else ""
        result_html = f"""
        <p><strong>Suggested design</strong> (auto-computed —
        <span style="color:#b00020">PRELIMINARY, requires engineering sign-off
        before quoting or confirming to the client</span>):</p>
        <ul>
          <li>w = {_fmt(b.w, ' mm')} (longitudinal) &times;
              l = {_fmt(b.l, ' mm')} (transverse) &times;
              h = {_fmt(b.result.overal_height, ' mm')}</li>
          <li>Total internal elastomer thickness: {_fmt(total_ti, ' mm')}</li>
          <li>n = {b.n}, ti = {_fmt(b.ti, ' mm')}, ts = {_fmt(b.ts, ' mm')},
              g = {b.g} N/mm&sup2;, bearing type {b.bearing_type}</li>
          <li><strong>msf used: {b.msf}</strong>{
              ' (searched -- the smallest catalog value that made this '
              'design feasible; confirm this margin is acceptable before '
              'sign-off)' if schedule.msf is None else ' (fixed, as specified for this schedule)'
          }</li>
          <li><strong>Minimum vertical load used for the Type B/Type C check:
              {_fmt(result.best_check.min_vertical_kN_used, ' kN')}</strong>{
              ' (<span style="color:#b00020">not stated in this schedule -- '
              '0 kN was assumed</span>; confirm the real minimum vertical load '
              'before relying on this design being Type B, if shown as one)'
              if result.best_check.min_vertical_assumed_zero
              else ' (as stated in this schedule)'
          }</li>
          <li>Plan area: {_fmt(b.plan_area, ' mm&sup2;', 0)} &mdash;
              Total volume: {_fmt(b.total_volume, ' mm&sup3;', 0)}</li>
          <li>{result.combinations_evaluated:,} geometries checked (smallest
              first; the rest could not beat the designs found);
              {result.feasible_count:,} passed every combination</li>{
              '<li><strong style="color:#b00020">The search hit its time limit '
              '-- this is the best design found so far, not a proven '
              'optimum.</strong></li>' if getattr(result, "timed_out", False) else ''
          }
        </ul>
        <p><strong>Per-combination check for the suggested design:</strong></p>
        <table border="1" cellpadding="4" cellspacing="0">
          <tr><th>Combination</th><th>Pass</th><th>Strain (inner)</th><th>Strain (outer)</th></tr>
          {checks_html}
        </table>
        """

    html = f"""
    <html><body style="font-family: Arial, sans-serif; font-size: 14px;">
    <h2>New bearing design request — {label}</h2>
    <p><strong>Project:</strong> {label}<br>
       <strong>Company:</strong> {_esc(submitter.company) or '—'}<br>
       <strong>Submitted by:</strong> {_esc(submitter.name)}<br>
       <strong>Email:</strong> {_esc(submitter.email)}<br>
       {"<strong>Phone:</strong> " + _esc(submitter.phone) + "<br>" if submitter.phone else ""}
    </p>
    {"<p><strong>Notes from submitter:</strong><br>" + _esc(submitter.notes) + "</p>" if submitter.notes else ""}
    {extraction_html}

    {result_html}

    <p><strong>Submitted schedule</strong> (envelope: max longitudinal
       {_fmt(schedule.max_longitudinal_mm, ' mm')}, max transverse
       {_fmt(schedule.max_transverse_mm, ' mm')}, max height
       {_fmt(schedule.max_height_mm, ' mm')}; &mu;={schedule.mu},
       msf={'searched' if schedule.msf is None else schedule.msf},
       min vertical load={'not stated (0 kN assumed)' if schedule.min_vertical_kN is None else f'{schedule.min_vertical_kN} kN'},
       esl={schedule.esl}):</p>
    <table border="1" cellpadding="4" cellspacing="0">
      <tr>
        <th>Limit state</th><th>Case</th><th>Vertical (kN)</th><th>Transverse (kN)</th>
        <th>Longitudinal (kN)</th><th>Long. disp. (mm)</th><th>Trans. disp. (mm)</th>
        <th>Rotation (mrad)</th><th>Trans. rotation (mrad)</th>
      </tr>
      {rows_html}
    </table>
    <p style="color:#666; font-size:12px; margin-top:24px;">
      This design was generated automatically by the AssaFlex bearing design
      tool and has not been reviewed by an engineer. Do not share it with the
      client as a final design until it has been checked.
    </p>
    </body></html>
    """
    return subject, html


def send_email(subject: str, html_body: str, to_addrs: list[str],
               attachments: Optional[List[Attachment]] = None) -> None:
    """Sends via the SMTP relay configured in webapp/config.py.

    Raises on failure -- the caller decides whether that should fail the
    whole request or just be logged (see main.py).
    """
    if not to_addrs:
        raise ValueError("No recipients configured (ENGINEERING_EMAILS / SALES_EMAILS empty)")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.SMTP_FROM
    msg["To"] = ", ".join(to_addrs)
    msg.set_content("This email requires an HTML-capable mail client.")
    msg.add_alternative(html_body, subtype="html")
    for att in attachments or []:
        maintype, _, subtype = att.content_type.partition("/")
        msg.add_attachment(att.data, maintype=maintype, subtype=subtype or "octet-stream",
                           filename=att.filename)

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        if config.SMTP_STARTTLS:
            server.starttls()
        if config.SMTP_USER:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)
