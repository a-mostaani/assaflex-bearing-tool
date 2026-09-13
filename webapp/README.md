# Bearing design request — public website integration

Lets a visitor on assaflex.com submit a bearing schedule through a form and
have a preliminary design computed automatically, with the result emailed
to engineering and sales for review — the visitor themselves never sees the
computed numbers, only an acknowledgement. See the main project README's
"Known issues" section for why this stays preliminary until AssaFlex's real
manufacturing catalog replaces the placeholder one.

Two pieces:

1. **`main.py`** — a small FastAPI backend (`/api/design-schedule`) that
   runs the existing `bearing_tool` optimizer and sends the notification
   email. Needs Python hosting somewhere (see below) — WordPress itself
   can't run this.
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

- **Does not show the computed design to the website visitor.** Per
  AssaFlex's choice, the result is preliminary and goes to engineering/sales
  for review first — the visitor only sees "your request has been
  received."
- **Does not store submissions anywhere** — each one only exists in the
  notification email. Add a database (or forward a copy to a CRM/shared
  inbox) if AssaFlex wants a running record for sales follow-up; this
  wasn't asked for yet.
- **Does not authenticate who can submit** — it's a public form, same as
  any "contact us" form. Add a CAPTCHA (e.g. Cloudflare Turnstile) if spam
  becomes a problem.
- **Uses the placeholder manufacturing catalog** (`default_catalog()`)
  unless `CATALOG_PATH` in `.env` points at a real one — see the main
  README's Known Issues.
