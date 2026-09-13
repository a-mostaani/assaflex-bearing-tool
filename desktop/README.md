# AssaFlex Bearing Design Tool — Windows desktop app

Turns the internal Streamlit tool into something colleagues can run by
double-clicking a file — no Python install, no terminal, no typed commands
on their end. It's a self-contained, portable Python environment (not a
single .exe — see "Why not a single .exe?" below), so the whole `desktop`
folder is the app.

## The two roles

- **One person builds it once**, on one Windows machine with normal
  internet access.
- **Everyone else just runs the result** — unzip, double-click, done.

If you're on the receiving end of an already-built folder (it has a
`runtime` folder in it), skip straight to "Running it" below.

## Building it (do this once)

1. Make sure this whole `desktop` folder — with `get-pip.py`,
   `requirements.txt`, `launcher.py`, the two build scripts, and
   `Run AssaFlex Bearing Tool.bat` — is on a Windows machine **with normal
   internet access**, sitting inside the full project (i.e. next to the
   project's `app.py`, `bearing_tool/`, and `schedules/` folders, exactly
   as delivered).
2. Double-click **`build_portable_app.bat`**.
3. A black window will appear and:
   - download the official Python 3.11 "embeddable" runtime from
     python.org (~10 MB),
   - install it into a new `runtime\` folder inside `desktop`,
   - install Streamlit and its dependencies into it from PyPI (this is
     the step that needs internet access — it downloads the same packages
     `pip install -r requirements.txt` would anywhere else),
   - copy the app's source (`app.py`, `bearing_tool\`, `schedules\`) into
     a new `app\` folder here.
4. When it says "Done!", the `desktop` folder is now a complete,
   self-contained app. Optionally delete `get-pip.py` and the downloaded
   `python-3.11.9-embed-amd64.zip` first (see the script's own output for
   the exact commands) to shrink it before sharing — they're only needed
   to build, not to run.
5. Zip the whole `desktop` folder and share it (a shared drive, Teams,
   OneDrive — email may reject it on size; expect roughly 150–250 MB,
   since it includes a full Python + Streamlit + pandas + pyarrow
   environment).

## Running it (everyone else)

1. Unzip the folder you were given, anywhere.
2. Double-click **`Run AssaFlex Bearing Tool.bat`**.
3. A black window opens (this is the app's server — leave it running) and
   your browser opens automatically to the tool a few seconds later.
4. To stop the app, close that black window.

No admin rights, no install dialog, no PATH changes — everything the app
needs lives inside this one folder.

## Troubleshooting

- **Windows SmartScreen / antivirus flags the .bat or the folder** — this
  is common for anything downloaded from outside the Microsoft Store and
  not code-signed. There's usually a "More info → Run anyway" option.
  Check with your IT team if group policy blocks it outright.
- **"numpy/pandas failed to load a DLL" on a colleague's machine** — a
  small number of Windows installations are missing the Microsoft Visual
  C++ Redistributable that some scientific Python packages need. It's a
  free, one-time install from Microsoft (search "Microsoft Visual C++
  Redistributable x64") and fixes this permanently.
- **The browser opens to a blank/error page** — usually means the black
  console window has an actual error printed in it; that message is the
  useful part, not the browser page.
- **Port 8765 already in use** — change the `--server.port` value in
  `launcher.py` to something else (e.g. `8766`) if this ever conflicts
  with something else on a colleague's machine.
- **Colleague is on Mac, not Windows** — this package is Windows-only (it
  bundles a Windows-native Python runtime). A Mac build would need the
  same process repeated with Python's macOS-specific distribution and
  wheels — ask if this comes up.

## Keeping it updated

There's no auto-update. When the underlying tool changes, whoever built it
re-runs `build_portable_app.bat` (it'll offer to rebuild `runtime\` from
scratch, or just re-copies `app\` if you keep the existing runtime — the
Python/Streamlit environment itself rarely needs to change, only the
`app\` folder), re-zips, and re-shares.

## Why not a single .exe?

Tools like PyInstaller can freeze a Python app into one .exe, but Streamlit
specifically is known to be fragile under that kind of freezing (it relies
on dynamically discovering its own installed files at runtime in ways
PyInstaller's static analysis often misses, breaking in version-specific
ways). The portable-folder approach above uses Python's own official,
supported "embeddable" distribution instead — it's slightly less slick
(a folder instead of one file) but far more reliable, and just as
zero-effort for colleagues to run.
