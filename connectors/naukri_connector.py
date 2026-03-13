"""
connectors/naukri_connector.py
────────────────────────────────
Naukri source connector.
Uses the Naukri Job API (official partner access).
Falls back gracefully if the API key is missing or the call fails.

Required config keys:
  naukri.api_key
  naukri.client_id
  naukri.client_secret
"""

from __future__ import annotations
import time
import logging
import requests
from datetime import datetime
from typing import Optional

from .base_connector import BaseConnector, CandidateProfile

logger = logging.getLogger(__name__)


class NaukriConnector(BaseConnector):

    def __init__(self, config: dict):
        super().__init__(config, "naukri")
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

    def _missing_required_keys(self) -> list[str]:
        required = ["api_key", "client_id", "client_secret"]
        return [k for k in required if not self.section_cfg.get(k, "").strip()]

    # ── Auth ─────────────────────────────────────────────────────────────

    def _get_access_token(self) -> str:
        """Fetch or refresh the OAuth access token."""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        resp = requests.post(
            f"{self.section_cfg['base_url']}/oauth/token",
            json={
                "client_id": self.section_cfg["client_id"],
                "client_secret": self.section_cfg["client_secret"],
                "grant_type": "client_credentials",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600) - 60
        return self._access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "x-api-key": self.section_cfg["api_key"],
            "Content-Type": "application/json",
        }

    # ── Fetch ─────────────────────────────────────────────────────────────

    def _do_fetch(self, query: str, location: str, max_results: int) -> list[CandidateProfile]:
        base_url = self.section_cfg.get("base_url", "https://www.naukri.com/api/v1")
        delay = self.section_cfg.get("request_delay_seconds", 2)
        fetched: list[CandidateProfile] = []
        page = 1
        page_size = min(max_results, 20)

        while len(fetched) < max_results:
            params = {
                "keywords": query,
                "location": location,
                "page": page,
                "pageSize": page_size,
            }
            resp = requests.get(
                f"{base_url}/resumes/search",
                headers=self._headers(),
                params=params,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()

            candidates = data.get("data", {}).get("candidates", [])
            if not candidates:
                break

            for raw in candidates:
                fetched.append(self._map(raw))
                if len(fetched) >= max_results:
                    break

            if len(candidates) < page_size:
                break
            page += 1
            time.sleep(delay)

        return fetched

    def _map(self, raw: dict) -> CandidateProfile:
        """Map a Naukri API candidate dict to CandidateProfile."""
        skills = [s.get("label", s) if isinstance(s, dict) else s
                  for s in raw.get("keySkills", [])]

        last_updated = None
        if ts := raw.get("modifiedOn"):
            try:
                last_updated = datetime.fromisoformat(ts)
            except ValueError:
                pass

        return CandidateProfile(
            raw_id=str(raw.get("resumeId", "")),
            source="naukri",
            name=raw.get("name", ""),
            email=raw.get("email", ""),
            phone=raw.get("mobile", ""),
            current_role=raw.get("currentDesignation", ""),
            current_company=raw.get("currentEmployer", ""),
            total_experience_years=float(raw.get("totalExperience", 0) or 0),
            skills=skills,
            location=raw.get("location", ""),
            notice_period_days=raw.get("noticePeriod"),
            profile_url=raw.get("profileLink", ""),
            last_updated=last_updated,
            raw_text=raw.get("resumeSummary", ""),
        )
