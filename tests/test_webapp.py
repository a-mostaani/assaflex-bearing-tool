"""Tests for the public-facing design-request API (webapp/).

Email sending is monkeypatched throughout -- these tests must never attempt
a real SMTP connection.
"""

from fastapi.testclient import TestClient

from webapp import main as webapp_main

client = TestClient(webapp_main.app)

VALID_PAYLOAD = {
    "schedule": {
        "label": "Test Bridge, bearing 1.1",
        "combinations": [
            {
                "limit_state": "ULS", "case": "Max Vertical",
                "vertical_kN": 2261, "transverse_kN": 3, "longitudinal_kN": 96,
                "long_displacement_mm": 11, "trans_displacement_mm": 0,
                "rotation_mrad": 4.65, "transverse_rotation_mrad": 0,
            },
            {
                "limit_state": "ULS", "case": "Max Rotation",
                "vertical_kN": 1150, "transverse_kN": 1, "longitudinal_kN": 95,
                "long_displacement_mm": 33, "trans_displacement_mm": 5,
                "rotation_mrad": 6.67, "transverse_rotation_mrad": 1.13,
            },
        ],
        "max_longitudinal_mm": 450, "max_transverse_mm": 600, "max_height_mm": 150,
        "mu": 0.3, "msf": 0.7, "esl": 0,
    },
    "submitter": {
        "name": "Jane Engineer", "company": "Acme Bridges",
        "email": "jane@example.com", "phone": "", "notes": "",
    },
}


def test_valid_submission_sends_one_email_and_does_not_leak_the_design(monkeypatch):
    sent = {}

    def fake_send_email(subject, html_body, to_addrs, attachments=None):
        sent["subject"] = subject
        sent["html_body"] = html_body
        sent["to_addrs"] = to_addrs

    monkeypatch.setattr(webapp_main, "send_email", fake_send_email)

    resp = client.post("/api/design-schedule", json=VALID_PAYLOAD)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "received"

    # The visitor-facing response must not contain the computed geometry --
    # only engineering/sales (via email) should see the numbers.
    assert "w=" not in body["message"] and "mm" not in body["message"]

    # Exactly one notification email, to both engineering and sales.
    assert sent["to_addrs"], "expected recipients"
    from webapp import config
    assert set(sent["to_addrs"]) == set(webapp_main.config.ENGINEERING_EMAILS
                                         + webapp_main.config.SALES_EMAILS)
    assert "PRELIMINARY" in sent["subject"]
    assert "Acme Bridges" in sent["html_body"]


def test_empty_combinations_rejected():
    payload = {**VALID_PAYLOAD, "schedule": {**VALID_PAYLOAD["schedule"], "combinations": []}}
    resp = client.post("/api/design-schedule", json=payload)
    assert resp.status_code == 400


def test_invalid_email_rejected():
    payload = {**VALID_PAYLOAD, "submitter": {**VALID_PAYLOAD["submitter"], "email": "not-an-email"}}
    resp = client.post("/api/design-schedule", json=payload)
    assert resp.status_code == 422


def test_msf_above_one_rejected():
    # Per Ash: cap msf at 1.0 everywhere -- rejected at the API boundary
    # (422) even for a caller posting directly, not just the form's own UI.
    payload = {**VALID_PAYLOAD, "schedule": {**VALID_PAYLOAD["schedule"], "msf": 1.1}}
    resp = client.post("/api/design-schedule", json=payload)
    assert resp.status_code == 422


def test_email_failure_is_reported_but_request_still_succeeds(monkeypatch):
    def failing_send_email(subject, html_body, to_addrs, attachments=None):
        raise RuntimeError("SMTP is down")

    monkeypatch.setattr(webapp_main, "send_email", failing_send_email)

    resp = client.post("/api/design-schedule", json=VALID_PAYLOAD)
    assert resp.status_code == 200  # never fail the visitor over an email hiccup
    assert resp.json()["status"] == "received_email_failed"


def test_health_check():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_correct_access_code_reveals_design_and_never_emails(monkeypatch):
    from webapp import config
    monkeypatch.setattr(config, "DESIGN_ACCESS_CODE", "let-me-in")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("send_email must not be called on the access-code path")
    monkeypatch.setattr(webapp_main, "send_email", fail_if_called)

    payload = {**VALID_PAYLOAD, "access_code": "let-me-in"}
    resp = client.post("/api/design-schedule", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "authorized"

    # This IS the one path where the visitor is meant to see the numbers.
    design = body["design"]
    assert design["feasible"] is True
    assert design["w_mm"] > 0 and design["l_mm"] > 0 and design["h_mm"] > 0
    assert design["n"] and design["ti_mm"]


def test_incorrect_access_code_rejected_without_computing_or_emailing(monkeypatch):
    from webapp import config
    monkeypatch.setattr(config, "DESIGN_ACCESS_CODE", "let-me-in")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("send_email must not be called on a rejected access code")
    monkeypatch.setattr(webapp_main, "send_email", fail_if_called)

    payload = {**VALID_PAYLOAD, "access_code": "wrong-code"}
    resp = client.post("/api/design-schedule", json=payload)
    assert resp.status_code == 401


def test_access_code_ignored_when_none_configured(monkeypatch):
    from webapp import config
    monkeypatch.setattr(config, "DESIGN_ACCESS_CODE", "")  # unset on the server

    payload = {**VALID_PAYLOAD, "access_code": "anything"}
    resp = client.post("/api/design-schedule", json=payload)
    assert resp.status_code == 401  # never matches an empty configured code


def test_blank_access_code_still_goes_through_the_normal_review_flow(monkeypatch):
    sent = {}
    monkeypatch.setattr(webapp_main, "send_email",
                         lambda subject, html_body, to_addrs, attachments=None: sent.setdefault("sent", True))

    payload = {**VALID_PAYLOAD, "access_code": ""}
    resp = client.post("/api/design-schedule", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "received"
    assert resp.json().get("design") is None
    assert sent.get("sent") is True


def test_design_out_reports_min_vertical_assumed_zero_when_not_stated(monkeypatch):
    from webapp import config
    monkeypatch.setattr(config, "DESIGN_ACCESS_CODE", "let-me-in")

    # VALID_PAYLOAD's schedule states no min_vertical_kN.
    payload = {**VALID_PAYLOAD, "access_code": "let-me-in"}
    resp = client.post("/api/design-schedule", json=payload)
    design = resp.json()["design"]
    assert design["min_vertical_assumed_zero"] is True
    assert design["min_vertical_kN_used"] == 0.0


def test_design_out_reports_a_stated_min_vertical_kN(monkeypatch):
    from webapp import config
    monkeypatch.setattr(config, "DESIGN_ACCESS_CODE", "let-me-in")

    schedule = {**VALID_PAYLOAD["schedule"], "min_vertical_kN": 500}
    payload = {**VALID_PAYLOAD, "schedule": schedule, "access_code": "let-me-in"}
    resp = client.post("/api/design-schedule", json=payload)
    design = resp.json()["design"]
    assert design["min_vertical_assumed_zero"] is False
    assert design["min_vertical_kN_used"] == 500


# ---------------------------------------------------------------------------
# Required project/company names
# ---------------------------------------------------------------------------

import copy

import pytest


@pytest.mark.parametrize("path", [("submitter", "company"), ("schedule", "label")])
@pytest.mark.parametrize("value", ["", "   "])
def test_company_and_project_name_are_required(monkeypatch, path, value):
    monkeypatch.setattr(webapp_main, "send_email",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no email expected")))
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload[path[0]][path[1]] = value
    resp = client.post("/api/design-schedule", json=payload)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Schedule upload / AI extraction (API call mocked -- never hits the network)
# ---------------------------------------------------------------------------

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extraction_fixtures import H3428_PATH, h3428_model_answer  # noqa: E402

from webapp import config as webapp_config  # noqa: E402
from webapp import extract as webapp_extract  # noqa: E402

PDF_BYTES = b"%PDF-1.4\n% fake test pdf\n"
UPLOAD_CODE = "letmein"
CODE = {"access_code": UPLOAD_CODE}


class _FakeToolUse:
    type = "tool_use"

    def __init__(self, data):
        self.input = data


class _FakeResponse:
    def __init__(self, data):
        self.content = [_FakeToolUse(data)]
        self.stop_reason = "tool_use"


class _FakeClient:
    def __init__(self, data):
        self.calls = []
        self._data = data
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._data)


@pytest.fixture
def extraction_on(monkeypatch):
    monkeypatch.setattr(webapp_config, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(webapp_config, "DESIGN_ACCESS_CODE", UPLOAD_CODE)
    monkeypatch.setattr(webapp_config, "EXTRACTIONS_PER_IP_PER_HOUR", 0)
    fake = _FakeClient(h3428_model_answer())
    monkeypatch.setattr(webapp_extract, "_client", lambda: fake)
    return fake


def test_extract_schedule_prefills_rows_matching_the_hand_transcription(extraction_on):
    from bearing_tool.schedule import BearingSchedule
    resp = client.post("/api/extract-schedule", data=CODE,
                       files={"file": ("H3428.pdf", PDF_BYTES, "application/pdf")})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ref = BearingSchedule.from_client_schedule_json(H3428_PATH)
    assert len(body["combinations"]) == len(ref.combinations) == 14
    for got, want in zip(body["combinations"], ref.combinations):
        assert got["limit_state"] == want.limit_state and got["case"] == want.case
        assert got["vertical_kN"] == want.vertical_kN
        assert got["rotation_mrad"] == want.rotation_mrad
        assert got["transverse_rotation_mrad"] == want.transverse_rotation_mrad
    assert (body["max_longitudinal_mm"], body["max_transverse_mm"], body["max_height_mm"]) == (450, 600, 100)
    assert body["warnings"]            # the model's own flag is passed through
    assert body["checks"]              # and the plain-code checks run

    # The PDF went to the model as a document block, with a forced tool call.
    call = extraction_on.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "record_bearing_schedule"}
    assert call["messages"][0]["content"][0]["type"] == "document"


def test_extract_schedule_rejects_wrong_types_and_oversize(extraction_on, monkeypatch):
    r = client.post("/api/extract-schedule", data=CODE, files={"file": ("x.docx", b"PK..", "application/msword")})
    assert r.status_code == 415
    r = client.post("/api/extract-schedule", data=CODE, files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 415
    monkeypatch.setattr(webapp_config, "MAX_UPLOAD_MB", 0)
    r = client.post("/api/extract-schedule", data=CODE, files={"file": ("x.pdf", PDF_BYTES, "application/pdf")})
    assert r.status_code == 413
    assert not extraction_on.calls  # none of these reached the paid API


def test_extract_schedule_unavailable_without_api_key(monkeypatch):
    monkeypatch.setattr(webapp_config, "ANTHROPIC_API_KEY", "")
    r = client.post("/api/extract-schedule", data=CODE, files={"file": ("x.pdf", PDF_BYTES, "application/pdf")})
    assert r.status_code == 503
    assert client.get("/api/features").json()["schedule_upload"] is False


def test_extract_schedule_reports_when_no_schedule_found(extraction_on):
    extraction_on._data = {"found_schedule": False, "combinations": [], "warnings": []}
    r = client.post("/api/extract-schedule", data=CODE, files={"file": ("x.pdf", PDF_BYTES, "application/pdf")})
    assert r.status_code == 422
    assert "couldn't find" in r.json()["detail"]


def test_extract_schedule_is_rate_limited_per_ip(extraction_on, monkeypatch):
    monkeypatch.setattr(webapp_config, "EXTRACTIONS_PER_IP_PER_HOUR", 2)
    webapp_main._upload_log.clear()
    headers = {"x-forwarded-for": "203.0.113.9"}
    codes = [client.post("/api/extract-schedule", headers=headers, data=CODE,
                         files={"file": ("x.pdf", PDF_BYTES, "application/pdf")}).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]
    webapp_main._upload_log.clear()


def test_validation_flags_unit_slips_and_swapped_values():
    data = h3428_model_answer()
    data["combinations"][1]["coincident_rotation_mrad"] = 0.00351   # given in rad
    data["combinations"][2]["vertical_kN"] = 5000                    # SLS Min > Max
    result = webapp_extract.build_result(data, model="test")
    joined = " ".join(result.checks)
    assert "unusually small" in joined
    assert "Min Vertical" in joined and "larger than Max Vertical" in joined


def test_uploaded_file_is_attached_to_the_engineering_email(monkeypatch):
    sent = {}

    def fake_send_email(subject, html_body, to_addrs, attachments=None):
        sent.update(html=html_body, attachments=attachments)

    monkeypatch.setattr(webapp_main, "send_email", fake_send_email)
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["submitter"]["company"] = "<b>Acme</b>"
    payload["source_file"] = {"filename": "schedule.pdf", "content_type": "application/pdf",
                              "data_base64": base64.b64encode(PDF_BYTES).decode()}
    payload["extraction"] = {"model": "claude-test", "warnings": ["SLS row: [rad] read as mrad"],
                             "checks": []}
    payload["upload_access_code"] = UPLOAD_CODE
    monkeypatch.setattr(webapp_config, "DESIGN_ACCESS_CODE", UPLOAD_CODE)
    resp = client.post("/api/design-schedule", json=payload)
    assert resp.status_code == 200
    [att] = sent["attachments"]
    assert att.filename == "schedule.pdf" and att.data == PDF_BYTES
    assert "read from an uploaded file by AI" in sent["html"]
    assert "[rad] read as mrad" in sent["html"]
    assert "<b>Acme</b>" not in sent["html"]  # visitor text is escaped


def test_submission_rejects_a_disguised_attachment(monkeypatch):
    monkeypatch.setattr(webapp_main, "send_email", lambda *a, **k: None)
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["source_file"] = {"filename": "x.exe", "content_type": "application/x-msdownload",
                              "data_base64": base64.b64encode(b"MZ").decode()}
    payload["upload_access_code"] = UPLOAD_CODE
    monkeypatch.setattr(webapp_config, "DESIGN_ACCESS_CODE", UPLOAD_CODE)
    assert client.post("/api/design-schedule", json=payload).status_code == 400


# ---------------------------------------------------------------------------
# Upload is for access-code holders only
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", ["", "wrong"])
def test_extract_schedule_requires_a_valid_access_code(extraction_on, code):
    r = client.post("/api/extract-schedule", data={"access_code": code},
                    files={"file": ("x.pdf", PDF_BYTES, "application/pdf")})
    assert r.status_code == 401
    assert not extraction_on.calls  # rejected before any paid API call


def test_upload_is_off_when_no_access_code_is_configured(extraction_on, monkeypatch):
    monkeypatch.setattr(webapp_config, "DESIGN_ACCESS_CODE", "")
    assert client.get("/api/features").json()["schedule_upload"] is False
    r = client.post("/api/extract-schedule", data={"access_code": "anything"},
                    files={"file": ("x.pdf", PDF_BYTES, "application/pdf")})
    assert r.status_code == 503
    assert not extraction_on.calls


@pytest.mark.parametrize("code", ["", "wrong"])
def test_submission_with_an_uploaded_file_requires_the_access_code(monkeypatch, code):
    monkeypatch.setattr(webapp_config, "DESIGN_ACCESS_CODE", UPLOAD_CODE)
    monkeypatch.setattr(webapp_main, "send_email",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no email expected")))
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["source_file"] = {"filename": "schedule.pdf", "content_type": "application/pdf",
                              "data_base64": base64.b64encode(PDF_BYTES).decode()}
    payload["upload_access_code"] = code
    assert client.post("/api/design-schedule", json=payload).status_code == 401


# ---------------------------------------------------------------------------
# Email delivery: Resend HTTPS API (Railway blocks SMTP on non-Pro plans)
# ---------------------------------------------------------------------------

import json as _json

from webapp import emailer as webapp_emailer


class _FakeHTTPResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_resend_is_used_when_its_key_is_set(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["body"] = _json.loads(req.data)
        return _FakeHTTPResponse()

    monkeypatch.setattr(webapp_config, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(webapp_config, "SMTP_FROM", "designs@assaflex.example")
    monkeypatch.setattr(webapp_emailer.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(webapp_emailer.smtplib, "SMTP",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("SMTP must not be used")))

    att = webapp_emailer.Attachment("schedule.pdf", "application/pdf", PDF_BYTES)
    webapp_emailer.send_email("Subj", "<p>hi</p>", ["eng@example.com"], attachments=[att])
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["auth"] == "Bearer re_test"
    body = captured["body"]
    assert body["from"] == "designs@assaflex.example" and body["to"] == ["eng@example.com"]
    assert base64.b64decode(body["attachments"][0]["content"]) == PDF_BYTES


def test_resend_error_is_reported_clearly(monkeypatch):
    import io
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {},
                                     io.BytesIO(b'{"message":"The assaflex.example domain is not verified."}'))

    monkeypatch.setattr(webapp_config, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(webapp_emailer.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(webapp_emailer.EmailConfigError, match="not verified"):
        webapp_emailer.send_email("Subj", "<p>hi</p>", ["eng@example.com"])


def test_unconfigured_smtp_says_what_to_set(monkeypatch):
    monkeypatch.setattr(webapp_config, "RESEND_API_KEY", "")
    monkeypatch.setattr(webapp_config, "SMTP_HOST", "smtp.example.com")
    with pytest.raises(webapp_emailer.EmailConfigError, match="RESEND_API_KEY"):
        webapp_emailer.send_email("Subj", "<p>hi</p>", ["eng@example.com"])


def test_email_test_endpoint_needs_the_code_and_reports_errors(monkeypatch):
    monkeypatch.setattr(webapp_config, "DESIGN_ACCESS_CODE", UPLOAD_CODE)
    assert client.post("/api/email-test", json={"access_code": "wrong"}).status_code == 401
    monkeypatch.setattr(webapp_config, "RESEND_API_KEY", "")
    monkeypatch.setattr(webapp_config, "SMTP_HOST", "smtp.example.com")
    r = client.post("/api/email-test", json={"access_code": UPLOAD_CODE}).json()
    assert r["ok"] is False and "RESEND_API_KEY" in r["error"]
