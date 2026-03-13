"""
main.py — PyInstaller entry point
──────────────────────────────────
This file is the exe target. It launches Streamlit programmatically
so that PyInstaller can bundle everything into a single folder.

Recruiters never see or touch this file.
"""

import os
import sys


def _resource(relative_path: str) -> str:
    """
    Resolve a path that works both in:
      - normal Python:    relative to this file's directory
      - frozen exe:       relative to PyInstaller's _MEIPASS temp folder
    """
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS          # bundled temp dir at runtime
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


if __name__ == "__main__":
    # Must be set BEFORE importing streamlit — tells it where its static
    # files live inside the bundle.
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

    from streamlit.web import cli as stcli

    app_path = _resource("app.py")

    sys.argv = [
        "streamlit", "run", app_path,
        "--server.headless=true",
        "--server.port=8501",
        "--server.address=localhost",
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())
