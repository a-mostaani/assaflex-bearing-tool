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

    def fake_send_email(subject, html_body, to_addrs):
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
    def failing_send_email(subject, html_body, to_addrs):
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
                         lambda subject, html_body, to_addrs: sent.setdefault("sent", True))

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
