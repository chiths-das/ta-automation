"""
connectors/source_manager.py
──────────────────────────────
Orchestrates all source connectors.

Key guarantee: if ANY connector is misconfigured, disabled, or throws —
the pipeline continues with results from the remaining sources.
The recruiter always gets results as long as at least one source works.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass

from .base_connector import CandidateProfile
from .naukri_connector import NaukriConnector
from .linkedin_connector import LinkedInConnector
from .resume_connector import ResumeConnector

logger = logging.getLogger(__name__)


@dataclass
class SourceSummary:
    """Returned alongside results so the UI can show which sources contributed."""
    naukri: int = 0
    linkedin: int = 0
    resume_dir: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @property
    def total(self) -> int:
        return self.naukri + self.linkedin + self.resume_dir

    @property
    def active_sources(self) -> list[str]:
        active = []
        if self.naukri:   active.append(f"Naukri ({self.naukri})")
        if self.linkedin: active.append(f"LinkedIn ({self.linkedin})")
        if self.resume_dir: active.append(f"Resume dir ({self.resume_dir})")
        return active


class SourceManager:
    """
    Single entry point for the rest of the pipeline.

    Usage:
        manager = SourceManager(config)
        candidates, summary = manager.fetch_all(query="Python Developer", location="Bengaluru")
        print(f"Got {summary.total} candidates from: {summary.active_sources}")
    """

    def __init__(self, config: dict):
        self.config = config
        # Register all connectors here — add new ones in one place
        self._connectors = {
            "naukri":     NaukriConnector(config),
            "linkedin":   LinkedInConnector(config),
            "resume_dir": ResumeConnector(config),
        }
        self._log_source_status()

    def _log_source_status(self):
        logger.info("── Source status ──────────────────────────────")
        for name, connector in self._connectors.items():
            status = "✓ enabled" if connector.is_enabled() else "✗ skipped"
            logger.info(f"  {name:<15} {status}")
        logger.info("───────────────────────────────────────────────")

    def fetch_all(
        self,
        query: str,
        location: str = "",
        max_per_source: int = 50,
    ) -> tuple[list[CandidateProfile], SourceSummary]:
        """
        Fetch from all enabled sources in parallel-ish (sequential for now,
        trivially parallelisable with ThreadPoolExecutor if needed).

        Returns:
            candidates: deduplicated list of CandidateProfile
            summary: per-source counts + any error messages
        """
        summary = SourceSummary()
        all_candidates: list[CandidateProfile] = []

        for name, connector in self._connectors.items():
            try:
                results = connector.fetch_candidates(query, location, max_per_source)
            except Exception as exc:
                # Belt-and-suspenders: base class already catches, but just in case
                msg = f"{name} failed unexpectedly: {exc}"
                logger.error(msg)
                summary.errors.append(msg)
                results = []

            count = len(results)
            if name == "naukri":     summary.naukri     = count
            if name == "linkedin":   summary.linkedin    = count
            if name == "resume_dir": summary.resume_dir  = count

            all_candidates.extend(results)

        deduped = self._deduplicate(all_candidates)
        logger.info(
            f"Total candidates: {len(deduped)} "
            f"(after dedup from {len(all_candidates)} raw)"
        )
        return deduped, summary

    # ── Deduplication ─────────────────────────────────────────────────────

    def _deduplicate(self, candidates: list[CandidateProfile]) -> list[CandidateProfile]:
        """
        Remove duplicates across sources using a priority fingerprint:
          1. Email (strongest signal)
          2. name + current_company (fuzzy)
          3. raw_id fingerprint (resume hash)

        LinkedIn profile beats Naukri beats resume_dir when same candidate
        appears in multiple sources (LinkedIn has richest structured data).
        """
        SOURCE_PRIORITY = {"linkedin": 0, "naukri": 1, "resume_dir": 2}

        # Sort so higher-priority sources win
        candidates = sorted(candidates, key=lambda c: SOURCE_PRIORITY.get(c.source, 99))

        seen_emails: set[str] = set()
        seen_fingerprints: set[str] = set()
        seen_name_company: set[str] = set()
        deduped: list[CandidateProfile] = []

        for c in candidates:
            # Email dedup
            if c.email:
                if c.email.lower() in seen_emails:
                    continue
                seen_emails.add(c.email.lower())

            # Fingerprint dedup (resume hash)
            if c.fingerprint:
                if c.fingerprint in seen_fingerprints:
                    continue
                seen_fingerprints.add(c.fingerprint)

            # Name + company dedup (fallback)
            if c.name and c.current_company:
                key = f"{c.name.lower()}|{c.current_company.lower()}"
                if key in seen_name_company:
                    continue
                seen_name_company.add(key)

            deduped.append(c)

        return deduped

    def status_report(self) -> dict:
        """Returns a dict suitable for display in the UI health check."""
        return {
            name: {
                "enabled": connector.is_enabled(),
                "type": connector.__class__.__name__,
            }
            for name, connector in self._connectors.items()
        }
