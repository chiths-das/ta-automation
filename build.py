#!/usr/bin/env python3
"""
build.py
─────────────────────────────────────────────────────────────────────
Builds the TA Automation distributable for recruiters.

Run once on the developer machine. Output is a folder (or zip) that
recruiters can run without installing Python or any libraries.

Usage:
    python build.py              # build for current platform
    python build.py --clean      # wipe build/ dist/ first
    python build.py --zip        # also create a zip ready to share

Requirements on the DEVELOPER machine only:
    pip install -r requirements.txt
    pip install pyinstaller

Recruiter machines need NOTHING pre-installed.
─────────────────────────────────────────────────────────────────────
"""

import argparse
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist" / "ta_automation"
BUILD = ROOT / "build"


def clean():
    print("Cleaning previous build...")
    for d in [DIST.parent, BUILD]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  Removed {d}")


def build():
    print(f"\nBuilding for {platform.system()} / {platform.machine()}")
    print("This takes 3–8 minutes on first run (PyTorch is large).\n")

    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "ta_automation.spec", "--noconfirm"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print("\nBuild failed. Check the output above.")
        sys.exit(1)

    # ── Copy extra files into the dist folder ──────────────────────────────
    extras = ["run.bat", "run.sh", "config.yaml", "README.md"]
    for name in extras:
        src = ROOT / name
        if src.exists():
            shutil.copy(src, DIST / name)
            print(f"  Copied {name}")

    # Create empty resumes/ directory placeholder
    (DIST / "resumes").mkdir(exist_ok=True)
    (DIST / "resumes" / ".gitkeep").touch()

    # ── Size report ────────────────────────────────────────────────────────
    total_mb = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / 1e6
    print(f"\n  Bundle size: {total_mb:.0f} MB")
    if total_mb > 800:
        print("  Note: large because PyTorch (sentence-transformers) is included.")
        print("  Consider using the lightweight build (--no-torch) for CPU-only scoring.")

    print(f"\n  Build complete: {DIST}")


def make_zip():
    zip_name = ROOT / "dist" / f"ta_automation_{platform.system().lower()}.zip"
    print(f"\nZipping to {zip_name}...")
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in DIST.rglob("*"):
            zf.write(file, file.relative_to(DIST.parent))
    size_mb = zip_name.stat().st_size / 1e6
    print(f"  Zip: {zip_name.name}  ({size_mb:.0f} MB)")
    return zip_name


def print_instructions():
    is_win = platform.system() == "Windows"
    print("""
═══════════════════════════════════════════════════════
  Distribution instructions
═══════════════════════════════════════════════════════

  DEVELOPER (you, one time):
    1. Share the zip file with each recruiter.
    2. Tell them their API keys (or pre-fill config.yaml
       before zipping if keys are shared).

  RECRUITER (no Python needed):
    1. Unzip the folder anywhere.
    2. Double-click run.bat (Windows) or run.sh (Mac).
    3. First run: fill in config.local.yaml, re-run.
    4. Browser opens at http://localhost:8501.

  WHAT'S INSIDE THE ZIP:
    ta_automation.exe / ta_automation  ← the app (Python bundled)
    config.yaml                        ← template (safe to share)
    run.bat / run.sh                   ← launchers
    resumes/                           ← drop PDFs/DOCX here
    README.md

  WHAT'S NOT INSIDE (recruiter creates these):
    config.local.yaml                  ← API keys (never share this)
    data/                              ← ChromaDB vector store (auto-created)

═══════════════════════════════════════════════════════
""")


def main():
    parser = argparse.ArgumentParser(description="Build TA Automation distributable")
    parser.add_argument("--clean", action="store_true", help="Clean before building")
    parser.add_argument("--zip", action="store_true", help="Create zip after building")
    args = parser.parse_args()

    if args.clean:
        clean()

    build()

    if args.zip:
        make_zip()

    print_instructions()


if __name__ == "__main__":
    main()
