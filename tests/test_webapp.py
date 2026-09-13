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
