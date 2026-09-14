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


def _list_env(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


def _int_env(name: str, default: int) -> int:
    """Like os.environ.get(name, default), but also falls back to default
    when the variable is *set but blank* -- e.g. a host's dashboard where a
    variable name was added with no value typed in, which is `""`, not
    unset, so a plain `.get(name, default)` would still crash on int()."""
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


# --- SMTP (works with Google Workspace, Microsoft 365, or any transactional
# email provider's SMTP relay -- e.g. SendGrid, Postmark -- since they all
# speak standard SMTP). ---
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.example.com")
SMTP_PORT = _int_env("SMTP_PORT", 587)
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "bearing-designs@assaflex.example")
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
