"""
Desktop-app entry point. Run via the bundled embeddable Python
(``runtime\\python.exe launcher.py``) — never call this with a system
Python, since it assumes it's running inside the bundled runtime.

Adds ``app/`` (the copied bearing_tool + app.py + schedules) to sys.path,
then hands off to Streamlit's own CLI exactly as ``streamlit run`` would --
Streamlit itself opens the default browser once the server is ready.
"""

import os
import sys


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.join(base_dir, "app")
    app_py = os.path.join(app_dir, "app.py")

    if not os.path.isfile(app_py):
        print("ERROR: app\\app.py not found next to launcher.py.")
        print("Did the build script finish successfully? See README.md.")
        input("Press Enter to close...")
        sys.exit(1)

    sys.path.insert(0, app_dir)

    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit", "run", app_py,
        "--server.port", "8765",
        "--server.address", "localhost",
        "--browser.gatherUsageStats", "false",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
