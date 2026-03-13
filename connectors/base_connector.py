"""
connectors/base_connector.py
─────────────────────────────
Abstract base class for all source connectors.
Every connector must implement fetch_candidates() and is expected
to handle its own errors gracefully — a failed connector must NOT
crash the pipeline; it logs and returns an empty list.
"""

from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CandidateProfile:
    """
    Normalised candidate schema shared across all sources.
    All fields are optional except source + raw_id so connectors
    can return partial profiles — the normalizer fills gaps later.
    """
    # Identity
    raw_id: str                          # Source-specific unique ID
    source: str                          # "naukri" | "linkedin" | "resume_dir"
    name: str = ""
    email: str = ""
    phone: str = ""

    # Role & experience
    current_role: str = ""
    current_company: str = ""
    total_experience_years: float = 0.0
    seniority: str = ""                  # junior | mid | senior | lead | staff

    # Skills (raw list — normalizer maps these to taxonomy)
    skills: list[str] = field(default_factory=list)

    # Education
    highest_degree: str = ""
    institution: str = ""

    # Location
    location: str = ""
    remote_preference: str = ""          # "remote" | "hybrid" | "onsite" | "any"

    # Profile metadata
    profile_url: str = ""
    last_updated: Optional[datetime] = None
    notice_period_days: Optional[int] = None

    # Raw text for embedding / LLM use
    raw_text: str = ""

    # Deduplication fingerprint (set by normalizer)
    fingerprint: str = ""


class BaseConnector(ABC):
    """
    All connectors follow this contract:
      1. __init__ receives the full config dict + optional section name
      2. is_enabled() returns False if the section is disabled or keys missing
      3. fetch_candidates() yields CandidateProfile objects
      4. Any exception inside fetch_candidates() is caught — log, return []
    """

    def __init__(self, config: dict, section: str):
        self.config = config
        self.section = section
        self.section_cfg = config.get(section, {})
        self.logger = logging.getLogger(self.__class__.__name__)

    def is_enabled(self) -> bool:
        """
        Returns True only if:
          - The section exists in config
          - enabled: true
          - All required keys are present and non-empty
        Subclasses can override to add extra checks.
        """
        if not self.section_cfg:
            self.logger.info(f"[{self.section}] Section missing from config — skipping.")
            return False
        if not self.section_cfg.get("enabled", False):
            self.logger.info(f"[{self.section}] Disabled in config — skipping.")
            return False
        missing = self._missing_required_keys()
        if missing:
            self.logger.warning(
                f"[{self.section}] Missing required config keys: {missing} — skipping."
            )
            return False
        return True

    def _missing_required_keys(self) -> list[str]:
        """Override in subclass to declare required config keys."""
        return []

    @abstractmethod
    def _do_fetch(self, query: str, location: str, max_results: int) -> list[CandidateProfile]:
        """
        Internal fetch implementation. Raise freely — caller catches.
        """
        ...

    def fetch_candidates(
        self,
        query: str,
        location: str = "",
        max_results: int = 50,
    ) -> list[CandidateProfile]:
        """
        Public entry point. Always safe to call:
        - Returns [] if not enabled
        - Returns [] and logs on any exception
        """
        if not self.is_enabled():
            return []
        try:
            results = self._do_fetch(query, location, max_results)
            self.logger.info(f"[{self.section}] Fetched {len(results)} candidates.")
            return results
        except Exception as exc:
            self.logger.error(
                f"[{self.section}] Fetch failed — source skipped. Error: {exc}",
                exc_info=True,
            )
            return []
