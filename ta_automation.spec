# ta_automation.spec
# ─────────────────────────────────────────────────────────────────
# PyInstaller spec — one-folder distribution.
# Recruiters get a zip; no Python installation needed.
#
# Build on developer machine:
#   pip install pyinstaller
#   pyinstaller ta_automation.spec --noconfirm
#
# Output folder to zip and ship:
#   dist/ta_automation/
# ─────────────────────────────────────────────────────────────────

import sys
from pathlib import Path
import streamlit
import sentence_transformers

block_cipher = None

# ── Locate Streamlit's static web assets (JS, CSS, fonts) ────────────────────
# These must be bundled or the browser shows a blank page.
streamlit_root = Path(streamlit.__file__).parent
streamlit_static = str(streamlit_root / "static")
streamlit_runtime = str(streamlit_root / "runtime")

# ── Locate sentence-transformers data files ───────────────────────────────────
st_root = Path(sentence_transformers.__file__).parent

# ─────────────────────────────────────────────────────────────────────────────

a = Analysis(
    ["main.py"],                        # ← entry point, not app.py
    pathex=["."],
    binaries=[],
    datas=[
        # ── App files ─────────────────────────────────────────────────────────
        ("app.py",          "."),       # Streamlit script (referenced at runtime)
        ("config.yaml",     "."),       # Template config shipped with the exe
        ("README.md",       "."),
        ("connectors",      "connectors"),

        # ── Streamlit static assets ───────────────────────────────────────────
        # Without these the browser loads a blank white page.
        (streamlit_static,   "streamlit/static"),
        (streamlit_runtime,  "streamlit/runtime"),

        # ── Sentence-transformers data ────────────────────────────────────────
        (str(st_root),      "sentence_transformers"),
    ],
    hiddenimports=[
        # Connectors (all loaded dynamically via import, not statically)
        "connectors",
        "connectors.base_connector",
        "connectors.naukri_connector",
        "connectors.linkedin_connector",
        "connectors.resume_connector",
        "connectors.source_manager",

        # PDF / DOCX parsing
        "pdfplumber",
        "pdfminer",
        "pdfminer.high_level",
        "pypdf",
        "docx",
        "docx.oxml",

        # ChromaDB — lots of lazy imports the analyser misses
        "chromadb",
        "chromadb.api",
        "chromadb.api.types",
        "chromadb.db.impl",
        "chromadb.db.impl.sqlite",
        "chromadb.segment",
        "chromadb.segment.impl.metadata",
        "chromadb.segment.impl.metadata.sqlite",
        "chromadb.segment.impl.vector",
        "chromadb.segment.impl.vector.local_hnsw",
        "chromadb.telemetry",
        "chromadb.telemetry.posthog",

        # Sentence transformers + torch
        "sentence_transformers",
        "sentence_transformers.models",
        "torch",
        "torch.nn",
        "transformers",
        "huggingface_hub",

        # OpenAI SDK
        "openai",
        "openai._models",
        "httpx",
        "httpcore",

        # Streamlit internals
        "streamlit",
        "streamlit.web",
        "streamlit.web.cli",
        "streamlit.web.server",
        "streamlit.web.bootstrap",
        "streamlit.runtime",
        "streamlit.runtime.scriptrunner",
        "streamlit.runtime.state",
        "altair",
        "pyarrow",
        "watchdog",
        "click",
        "tornado",
        "validators",
        "importlib_metadata",

        # YAML
        "yaml",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Things we don't need — reduces bundle size
        "matplotlib",
        "notebook",
        "IPython",
        "scipy",
        "PIL",
        "cv2",
        "skimage",
        "pytest",
        "black",
        "mypy",
        "pylint",
        "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ta_automation",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                           # compress — saves ~30% on Windows
    console=True,                       # show terminal window (useful for errors)
    icon=None,                          # add a .ico file path here if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ta_automation",
)
