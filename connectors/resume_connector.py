"""
connectors/resume_connector.py
────────────────────────────────
Resume directory source connector.

Supports three path types — configured via resume_directory.path:
  • Local folder          path: "./resumes"
  • OneDrive (mounted)    path: "C:/Users/name/OneDrive/Resumes"
                          path: "/Users/name/OneDrive - Company/Resumes"  (Mac)
  • Google Drive (mounted) via Google Drive for Desktop
                          path: "G:/My Drive/Resumes"
                          path: "/Volumes/GoogleDrive/My Drive/Resumes"   (Mac)

All three behave identically once mounted — they're just filesystem paths.
The connector also supports the rclone-mount pattern for headless machines.

No required config keys — if path doesn't exist, logs a warning and returns [].
"""

from __future__ import annotations
import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base_connector import BaseConnector, CandidateProfile

logger = logging.getLogger(__name__)


# ── Optional heavy deps — imported lazily so missing libs don't crash startup ──

def _try_import(module: str):
    try:
        import importlib
        return importlib.import_module(module)
    except ImportError:
        return None


class ResumeConnector(BaseConnector):
    """
    Parses PDF and DOCX resumes from any mounted filesystem path.
    Uses a simple LLM-free NLP pass for speed; LLM enrichment is
    done later by the normalizer on the raw_text field.
    """

    SUPPORTED_FORMATS = {".pdf", ".docx", ".doc", ".txt"}

    def __init__(self, config: dict):
        super().__init__(config, "resume_directory")

    def _missing_required_keys(self) -> list[str]:
        # Path is optional — if missing we warn but don't hard-fail
        return []

    def _resolve_paths(self) -> list[Path]:
        """
        Normalise path config into a list of resolved Path objects.
        Accepts either a single string or a list of strings:
            path: "./resumes"
            path: ["./resumes", "./my-resumes", "/mnt/shared/resumes"]
        Only paths that actually exist on disk are returned.
        """
        raw = self.section_cfg.get("path", [])
        if isinstance(raw, str):
            raw = [raw]                     # wrap bare string in a list

        valid: list[Path] = []
        for p in raw:
            resolved = Path(p).expanduser().resolve()
            if resolved.exists():
                valid.append(resolved)
            else:
                self.logger.warning(
                    f"[resume_directory] Path does not exist — skipping: {resolved}\n"
                    "  • For OneDrive: ensure OneDrive is running and the folder is synced.\n"
                    "  • For Google Drive: ensure 'Google Drive for Desktop' is running.\n"
                    "  • For a network share: ensure the drive is mounted."
                )
        return valid

    def is_enabled(self) -> bool:
        if not self.section_cfg.get("enabled", False):
            self.logger.info("[resume_directory] Disabled in config — skipping.")
            return False
        raw = self.section_cfg.get("path", [])
        if not raw:
            self.logger.warning("[resume_directory] No path configured — skipping.")
            return False
        if not self._resolve_paths():
            self.logger.warning(
                "[resume_directory] None of the configured paths exist — skipping source."
            )
            return False
        return True

    # ── Main fetch ────────────────────────────────────────────────────────

    def _do_fetch(self, query: str, location: str, max_results: int) -> list[CandidateProfile]:
        formats = {
            f".{ext.lstrip('.')}" for ext in
            self.section_cfg.get("formats", ["pdf", "docx", "doc"])
        }

        # Collect files from every valid path, deduplicate by absolute path
        seen_paths: set[Path] = set()
        all_files: list[Path] = []
        for directory in self._resolve_paths():
            self.logger.info(f"[resume_directory] Scanning: {directory}")
            for f in directory.rglob("*"):
                if f.is_file() and f.suffix.lower() in formats and f not in seen_paths:
                    seen_paths.add(f)
                    all_files.append(f)

        self.logger.info(
            f"[resume_directory] Found {len(all_files)} resume files across "
            f"{len(self._resolve_paths())} director(ies)."
        )

        results: list[CandidateProfile] = []
        for resume_file in all_files[:max_results]:
            try:
                profile = self._parse_file(resume_file)
                if profile:
                    results.append(profile)
            except Exception as exc:
                self.logger.warning(f"[resume_directory] Failed to parse {resume_file.name}: {exc}")
        return results

    # ── Per-file parsing ──────────────────────────────────────────────────

    def _parse_file(self, path: Path) -> Optional[CandidateProfile]:
        suffix = path.suffix.lower()
        text = ""

        if suffix == ".pdf":
            text = self._read_pdf(path)
        elif suffix in {".docx", ".doc"}:
            text = self._read_docx(path)
        elif suffix == ".txt":
            text = path.read_text(encoding="utf-8", errors="ignore")

        if not text.strip():
            self.logger.debug(f"Empty text from {path.name} — skipping.")
            return None

        return self._extract_profile(text, path)

    def _read_pdf(self, path: Path) -> str:
        pdfplumber = _try_import("pdfplumber")
        if pdfplumber:
            with pdfplumber.open(path) as pdf:
                return "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )
        # Fallback: pypdf
        pypdf = _try_import("pypdf")
        if pypdf:
            reader = pypdf.PdfReader(str(path))
            return "\n".join(
                page.extract_text() or "" for page in reader.pages
            )
        raise ImportError("Install pdfplumber or pypdf: pip install pdfplumber")

    def _read_docx(self, path: Path) -> str:
        docx = _try_import("docx")
        if docx:
            doc = docx.Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs)
        raise ImportError("Install python-docx: pip install python-docx")

    # ── Lightweight profile extraction (no LLM) ───────────────────────────

    def _extract_profile(self, text: str, path: Path) -> CandidateProfile:
        """
        Heuristic extraction for speed. The normalizer will later call the
        LLM on raw_text for anything it can't reliably detect here.
        """
        fingerprint = hashlib.md5(text.encode()).hexdigest()
        last_modified = datetime.fromtimestamp(path.stat().st_mtime)

        name = self._extract_name(text, path)
        email = self._extract_email(text)
        phone = self._extract_phone(text)
        skills = self._extract_skills(text)
        exp_years = self._extract_experience_years(text)

        return CandidateProfile(
            raw_id=fingerprint,
            source="resume_dir",
            name=name,
            email=email,
            phone=phone,
            skills=skills,
            total_experience_years=exp_years,
            last_updated=last_modified,
            profile_url=str(path),
            raw_text=text[:4000],          # Cap for LLM token budget
            fingerprint=fingerprint,
        )

    # ── Heuristic helpers ─────────────────────────────────────────────────

    def _extract_name(self, text: str, path: Path) -> str:
        # First non-empty line that looks like a name (2–4 words, title-case, no digits)
        for line in text.splitlines()[:10]:
            line = line.strip()
            words = line.split()
            if (2 <= len(words) <= 4
                    and all(w[0].isupper() for w in words if w)
                    and not any(c.isdigit() for c in line)):
                return line
        # Fallback: stem of filename
        return path.stem.replace("_", " ").replace("-", " ").title()

    def _extract_email(self, text: str) -> str:
        match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        return match.group(0) if match else ""

    def _extract_phone(self, text: str) -> str:
        match = re.search(
            r"(\+?\d{1,3}[\s\-]?)?(\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4})", text
        )
        return match.group(0).strip() if match else ""

    def _extract_skills(self, text: str) -> list[str]:
        """
        Match against a common tech skill vocabulary.
        The normalizer / LLM pass will expand this later.
        """
        KNOWN_SKILLS = {
            "python", "java", "javascript", "typescript", "go", "rust", "c++",
            "c#", "ruby", "scala", "kotlin", "swift", "r",
            "react", "angular", "vue", "node.js", "nodejs", "django", "flask",
            "fastapi", "spring", "rails",
            "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
            "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
            "kafka", "rabbitmq", "spark", "hadoop",
            "machine learning", "deep learning", "nlp", "llm",
            "pandas", "numpy", "scikit-learn", "pytorch", "tensorflow",
            "sql", "git", "ci/cd", "jenkins", "github actions",
            "rest api", "graphql", "microservices", "agile", "scrum",
        }
        text_lower = text.lower()
        found = []
        for skill in KNOWN_SKILLS:
            if re.search(r"\b" + re.escape(skill) + r"\b", text_lower):
                found.append(skill)
        return found

    def _extract_experience_years(self, text: str) -> float:
        """
        Look for patterns like '5 years', '5+ years of experience',
        'experience: 7 years', etc.
        """
        patterns = [
            r"(\d+(?:\.\d+)?)\+?\s*years?\s+(?:of\s+)?(?:total\s+)?experience",
            r"experience\s*[:\-]?\s*(\d+(?:\.\d+)?)\+?\s*years?",
            r"(\d+(?:\.\d+)?)\+?\s*yrs?\s+(?:of\s+)?exp",
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return 0.0
