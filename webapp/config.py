"""
Configuration for the bearing-design-request web service, loaded from
environment variables (a local ``.env`` file when present -- see
``webapp/.env.example``). Nothing here is a secret checked into git; every
real value (SMTP credentials, destination addresses, allowed origin) is
supplied at deploy time.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def _env(name: str, default: str) -> str:
    """Like os.environ.get(name, default), but also falls back to default
    when the variable is *set but blank* -- e.g. a host's dashboard where a
    variable name was added with no value typed in, which is `""`, not
    unset, so a plain `.get(name, default)` would silently stay `""`."""
    raw = os.environ.get(name)
    return raw if raw else default


def _list_env(name: str, default: str = "") -> list[str]:
    raw = _env(name, default)
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


def _int_env(name: str, default: int) -> int:
    raw = _env(name, str(default)).strip()
    return int(raw) if raw else default


# Seconds the schedule search may run before it stops and reports what it
# has (see find_optimal_design_for_schedule's time_budget_s). Kept well under
# the ~5 minute point where browsers/Railway's proxy give up on the request,
# so a pathological submission gets a clear message instead of "Couldn't
# reach the server".
SEARCH_TIME_BUDGET_S = _int_env("SEARCH_TIME_BUDGET_S", 90)


# --- Schedule upload (AI extraction, see webapp/extract.py). Leave
# ANTHROPIC_API_KEY blank to turn uploads off; the form then still works by
# hand. ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
EXTRACTION_MODEL = _env("EXTRACTION_MODEL", "claude-opus-5-5")
EXTRACTION_TIMEOUT_S = _int_env("EXTRACTION_TIMEOUT_S", 180)
MAX_UPLOAD_MB = _int_env("MAX_UPLOAD_MB", 10)
# Each extraction is a paid API call, so a single visitor (by IP) is limited
# to this many uploads per hour. 0 disables the limit.
EXTRACTIONS_PER_IP_PER_HOUR = _int_env("EXTRACTIONS_PER_IP_PER_HOUR", 10)


# --- SMTP (works with Google Workspace, Microsoft 365, or any transactional
# email provider's SMTP relay -- e.g. SendGrid, Postmark -- since they all
# speak standard SMTP). ---
SMTP_HOST = _env("SMTP_HOST", "smtp.example.com")
SMTP_PORT = _int_env("SMTP_PORT", 587)
SMTP_USER = os.environ.get("SMTP_USER", "")  # no sensible non-empty default
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")  # no sensible non-empty default
SMTP_FROM = _env("SMTP_FROM", "bearing-designs@assaflex.example")
# Most relays (587) need STARTTLS; set to "false" only for a local/dev
# debugging SMTP server that doesn't support it.
SMTP_STARTTLS = os.environ.get("SMTP_STARTTLS", "true").lower() != "false"

# --- Who gets notified. Comma-separated; put more than one address per team
# if needed (e.g. a personal inbox + a shared team inbox). ---
ENGINEERING_EMAILS = _list_env("ENGINEERING_EMAILS", "engineering@assaflex.example")
SALES_EMAILS = _list_env("SALES_EMAILS", "sales@assaflex.example")

# --- CORS: the website origin(s) allowed to call this API. Set to the real
# assaflex.com domain (and any staging domain) before going live. ---
ALLOWED_ORIGINS = _list_env("ALLOWED_ORIGINS", "https://www.assaflex.example")

# --- Manufacturing catalog the optimizer searches. Point this at a real,
# maintained JSON file (see bearing_tool/catalog.py's Catalog.to_json) once
# AssaFlex's actual manufacturing constraints replace the placeholder
# defaults -- see the main README's Known Issues #3. ---
CATALOG_PATH = os.environ.get("CATALOG_PATH", "")  # "" = use catalog.default_catalog()

# --- Optional shared access code that lets a visitor see the computed
# design directly on the page instead of routing it through engineering/
# sales for review (see main.py's `access_code` handling). Deliberately no
# non-empty default: leaving this unset disables the bypass entirely (any
# access code typed into the form is then always rejected), rather than
# silently falling back to a guessable placeholder value. ---
DESIGN_ACCESS_CODE = os.environ.get("DESIGN_ACCESS_CODE", "")
