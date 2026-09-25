# Bearing design request — public website integration

Lets a visitor on assaflex.com submit a bearing schedule through a form and
have a preliminary design computed automatically. The form offers two
paths, chosen by the visitor:

- **Send for review** (the default) — the computed design is emailed to
  engineering and sales; the visitor only ever sees an acknowledgement,
  never the numbers. See the main project README's "Known issues" section
  for why this stays preliminary until AssaFlex's real manufacturing
  catalog replaces the placeholder one.
- **I have an access code** — if the visitor enters the shared
  `DESIGN_ACCESS_CODE` (see below), the design is shown directly on the
  page instead, and **no email is sent at all** for that request (a
  correct code is a trusted bypass, not just an alternate view — there is
  deliberately no record of it beyond this). Meant for AssaFlex staff or a
  trusted distributor who wants the number immediately rather than waiting
  on a review. Leave `DESIGN_ACCESS_CODE` unset to disable this path
  entirely — the form still shows the option, but any code typed in is
  always rejected.

Two pieces:

1. **`main.py`** — a small FastAPI backend (`/api/design-schedule`) that
   runs the existing `bearing_tool` optimizer and sends the notification
   email. Needs Python hosting somewhere (see below) — WordPress itself
   can't run this. The access-code-authorized path also returns a branded
   "AssaFlex Calculation Document" (`document_html` on the response) for the
   winning design, matching the internal Streamlit app's own report; a PDF
   version of the same document is available via `POST
   /api/design-document.pdf` (same request body, same access-code gate).
2. **`static/design-request-form.html`** — a self-contained HTML/CSS/JS
   page with the actual form (dynamic add/remove rows for load
   combinations). Embed this in WordPress; it calls the backend above.

## 1. Configure

```bash
cp webapp/.env.example webapp/.env
# then edit webapp/.env with real SMTP credentials, recipient addresses,
# and the real assaflex.com domain for ALLOWED_ORIGINS
```

`SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD` can point at whatever AssaFlex
already uses to send email (Google Workspace, Microsoft 365, or a
transactional provider like SendGrid/Postmark's SMTP relay) — no code
changes needed, just the `.env` values.

If you want the "I have an access code" bypass enabled, also set
`DESIGN_ACCESS_CODE` to a shared secret and tell whoever should have it
out of band (it's never shown anywhere in the UI). Leave it blank to
disable that option.

## 2. Run locally to test

```bash
pip install -r webapp/requirements.txt
uvicorn webapp.main:app --reload --port 8000
```

Then open `webapp/static/design-request-form.html` directly in a browser
(edit the `API_BASE` line near the top of its `<script>` to
`http://localhost:8000` first), fill in a test schedule, and submit — check
that the notification email arrives.

## 3. Deploy the backend

This is a standard small FastAPI app — deploy it however AssaFlex normally
hosts backend services. Straightforward options:

- **A small VM/VPS**: install `webapp/requirements.txt`, run with
  `uvicorn webapp.main:app --host 0.0.0.0 --port 8000` behind a process
  manager (systemd, supervisor) and a reverse proxy (nginx/Caddy) for
  HTTPS.
- **Any other container platform** (Render, Fly.io, a company AWS/GCP
  account, etc.): use the provided `Dockerfile` —
  ```bash
  docker build -f webapp/Dockerfile -t assaflex-bearing-webapp .
  docker run -p 8000:8000 --env-file webapp/.env assaflex-bearing-webapp
  ```

Either way, the backend needs to end up reachable over HTTPS at some URL
(e.g. `https://bearing-api.assaflex.com`) that the WordPress site can call.

### Deploying on Railway specifically

The repo root includes `railway.json`, which tells Railway to build
`webapp/Dockerfile` (build context = repo root, so the sibling
`bearing_tool/` package is included — same as the manual `docker build`
command above). Two ways to deploy:

1. **From the Railway dashboard** (no CLI needed):
   - New Project → **Deploy from GitHub repo** → pick this repo (push it to
     GitHub first if it isn't already).
   - Railway detects `railway.json` and builds `webapp/Dockerfile`
     automatically.
   - Under the new service's **Variables** tab, add everything from
     `webapp/.env.example` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
     `SMTP_PASSWORD`, `SMTP_FROM`, `ENGINEERING_EMAILS`, `SALES_EMAILS`,
     `ALLOWED_ORIGINS`, optionally `CATALOG_PATH`) — Railway injects these
     as real environment variables, so nothing needs a committed `.env`
     file. Leave `ALLOWED_ORIGINS` as `*` for initial testing if you don't
     have the WordPress domain finalized yet, then lock it down to the real
     `https://www.assaflex.com` before going live.
   - Under **Settings → Networking**, click **Generate Domain** to get a
     public HTTPS URL (something like `https://<service>.up.railway.app`)
     — that's the URL to put in `window.AF_API_BASE` when embedding the
     form (see step 4 below), or point AssaFlex's own domain at it later
     via a custom domain in the same Networking tab.
   - Every push to the connected branch redeploys automatically.
2. **From the Railway CLI**, run from the repo root on a machine with
   normal internet access:
   ```bash
   npm i -g @railway/cli   # or: brew install railway
   railway login
   railway init            # creates/links a Railway project
   railway up              # builds webapp/Dockerfile and deploys
   railway variables --set SMTP_HOST=... --set SMTP_USER=... # etc, or use the dashboard
   railway domain          # generates the public HTTPS URL
   ```

Either path ends the same way: a live HTTPS URL for `ALLOWED_ORIGINS`/
`window.AF_API_BASE` and a service that redeploys itself on future pushes.

## Schedule upload (AI extraction)

Visitors can upload their bearing schedule (PDF, PNG or JPEG) instead of
typing it in. `POST /api/extract-schedule` sends the file to Claude
(`webapp/extract.py`), which fills a fixed schema mirroring EN 1337-1:2000
Table 1. The rows are then flattened by the same rules as a hand-transcribed
schedule (`BearingSchedule.from_client_schedule_dict`) and sanity-checked in
plain code (unit slips, max/min ordering, a missing envelope…).

Nothing extracted is designed or emailed automatically. The form is
pre-filled with the values highlighted, the visitor must tick "I've checked
the values" before submitting, and the engineering email says the values
were read by AI, lists what was flagged, and carries the original file as an
attachment.

Settings (Railway → Variables):

| Variable | Default | |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(blank)* | Required to turn uploads on. Blank hides the upload option; the form still works by hand. |
| `EXTRACTION_MODEL` | `claude-opus-5-5` | Model used to read the file. |
| `EXTRACTION_TIMEOUT_S` | `180` | |
| `MAX_UPLOAD_MB` | `10` | |
| `EXTRACTIONS_PER_IP_PER_HOUR` | `10` | Each upload is a paid API call; 0 disables the limit. |

Accuracy check against a hand transcription (one paid API call):

    ANTHROPIC_API_KEY=... python -m webapp.check_extraction \
        reference/H3428_Bridge_Bearing_Drawings_1.pdf schedules/H3428_A0_A5_bearing_1.1.json

## 4. Embed the form in WordPress

WordPress can't run the Python backend, but it can host the static form
page and call out to wherever the backend ends up:

1. Add a new Page (or a section of an existing one).
2. Add a **Custom HTML** block.
3. Paste in the contents of `static/design-request-form.html` **between**
   its `<body>` tags only (the `<style>` and `<script>` blocks included) —
   not the surrounding `<html>`/`<head>`, since WordPress provides those.
4. Just above the `<script>` tag's closing `</script>`, or in a separate
   Custom HTML block right before it, set the backend URL:
   ```html
   <script>window.AF_API_BASE = "https://bearing-api.assaflex.com";</script>
   ```
   (place this *before* the form's own `<script>` block runs, since it
   reads `window.AF_API_BASE` on load).
5. Update `ALLOWED_ORIGINS` in `webapp/.env` to match the real domain the
   page is served from (e.g. `https://www.assaflex.com`), then restart the
   backend — the browser will block the form's request otherwise (CORS).

If your WordPress theme's Custom HTML block strips `<script>` tags (some
security plugins do this), embed the page as an `<iframe>` instead:

```html
<iframe src="https://bearing-api.assaflex.com/static/design-request-form.html"
        style="width:100%; min-height:1400px; border:0;"></iframe>
```

(FastAPI can serve the static file directly — see the commented-out
`app.mount(...)` line at the bottom of `main.py` if you go this route.)

## What this deliberately does NOT do (yet)

- **Does not show the computed design to the website visitor, unless they
  use the access-code path.** Per AssaFlex's choice, the default is that
  the result is preliminary and goes to engineering/sales for review first
  — the visitor only sees "your request has been received." The access
  code is a deliberate, separate bypass of that (see above), not a way
  around it.
- **The access code is a single shared secret with no expiry, rotation, or
  per-user tracking** — anyone who has it can see any schedule's computed
  design, and there's no log of who used it (since that request path
  skips the email entirely, by design). Fine for a small number of trusted
  people; rotate `DESIGN_ACCESS_CODE` in Railway if it needs to be revoked.
- **Does not store submissions anywhere** — a normal (reviewed) submission
  only exists in the notification email, and an access-code submission
  leaves no record at all. Add a database (or forward a copy to a CRM/
  shared inbox) if AssaFlex wants a running record for sales follow-up;
  this wasn't asked for yet.
- **Does not authenticate who can submit** — it's a public form, same as
  any "contact us" form. Add a CAPTCHA (e.g. Cloudflare Turnstile) if spam
  becomes a problem (this matters more now that a correct access code
  reveals real numbers to whoever submits).
- **Uses the placeholder manufacturing catalog** (`default_catalog()`)
  unless `CATALOG_PATH` in `.env` points at a real one — see the main
  README's Known Issues.
