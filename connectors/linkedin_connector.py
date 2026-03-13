"""
connectors/linkedin_connector.py
──────────────────────────────────
LinkedIn Recruiter source connector.
Uses LinkedIn Recruiter API (requires partner / enterprise access).
Falls back gracefully if credentials are missing or the call fails.

Required config keys:
  linkedin.client_id
  linkedin.client_secret
  linkedin.access_token
"""

from __future__ import annotations
import time
import requests
from datetime import datetime
from typing import Optional

from .base_connector import BaseConnector, CandidateProfile


class LinkedInConnector(BaseConnector):

    def __init__(self, config: dict):
        super().__init__(config, "linkedin")

    def _missing_required_keys(self) -> list[str]:
        required = ["client_id", "client_secret", "access_token"]
        return [k for k in required if not self.section_cfg.get(k, "").strip()]

    # ── Auth ─────────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.section_cfg['access_token']}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    # ── Fetch ─────────────────────────────────────────────────────────────

    def _do_fetch(self, query: str, location: str, max_results: int) -> list[CandidateProfile]:
        base_url = self.section_cfg.get("base_url", "https://api.linkedin.com/v2")
        delay = self.section_cfg.get("request_delay_seconds", 3)
        fetched: list[CandidateProfile] = []
        start = 0
        page_size = min(max_results, 25)

        while len(fetched) < max_results:
            params = {
                "keywords": query,
                "location": location,
                "count": page_size,
                "start": start,
            }
            resp = requests.get(
                f"{base_url}/talentSearchProfiles",
                headers=self._headers(),
                params=params,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()

            elements = data.get("elements", [])
            if not elements:
                break

            for raw in elements:
                fetched.append(self._map(raw))
                if len(fetched) >= max_results:
                    break

            paging = data.get("paging", {})
            total = paging.get("total", 0)
            start += page_size
            if start >= total or len(elements) < page_size:
                break
            time.sleep(delay)

        return fetched

    def _map(self, raw: dict) -> CandidateProfile:
        """Map LinkedIn Recruiter profile to CandidateProfile."""
        profile = raw.get("profile", raw)

        # Skills from endorsedSkills or skills
        skills = []
        for sk in profile.get("skills", {}).get("elements", []):
            name = sk.get("name", "")
            if name:
                skills.append(name)

        # Experience
        exp_list = profile.get("experience", {}).get("elements", [])
        current_role, current_company = "", ""
        total_years = 0.0
        for exp in exp_list:
            if exp.get("current", False):
                current_role = exp.get("title", "")
                current_company = exp.get("companyName", "")
            years = exp.get("durationInMonths", 0) / 12
            total_years += years

        first = profile.get("firstName", {})
        last = profile.get("lastName", {})
        name = f"{first.get('localized', {}).get('en_US', '')} {last.get('localized', {}).get('en_US', '')}".strip()

        location_info = profile.get("location", {})
        location_str = location_info.get("name", "")

        profile_id = profile.get("publicIdentifier", str(raw.get("entityUrn", "")))

        return CandidateProfile(
            raw_id=profile_id,
            source="linkedin",
            name=name,
            current_role=current_role,
            current_company=current_company,
            total_experience_years=round(total_years, 1),
            skills=skills,
            location=location_str,
            profile_url=f"https://www.linkedin.com/in/{profile_id}",
            raw_text=profile.get("summary", ""),
        )
