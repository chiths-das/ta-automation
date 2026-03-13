"""
normalizer.py
─────────────────────────────────────────────────────────────
Normalises raw CandidateProfile objects from any source into a
consistent, scoring-ready format.

Responsibilities:
  • Skill taxonomy mapping  (JS → JavaScript, ML → Machine Learning)
  • Seniority inference from title / experience
  • Fingerprint generation for deduplication
  • LLM enrichment for resume-dir profiles with missing structure
"""

from __future__ import annotations
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from connectors.base_connector import CandidateProfile

logger = logging.getLogger(__name__)

# ── Skill taxonomy ──────────────────────────────────────────────────────
# Maps common aliases / abbreviations to canonical names
SKILL_ALIASES: dict[str, str] = {
    "js": "JavaScript", "ts": "TypeScript", "py": "Python",
    "ml": "Machine Learning", "dl": "Deep Learning",
    "nlp": "NLP", "llm": "LLM", "gen ai": "Generative AI",
    "node": "Node.js", "nodejs": "Node.js",
    "react.js": "React", "reactjs": "React",
    "vue.js": "Vue", "vuejs": "Vue",
    "postgres": "PostgreSQL", "pg": "PostgreSQL",
    "mongo": "MongoDB", "k8s": "Kubernetes",
    "tf": "Terraform", "gcp": "Google Cloud",
    "aws lambda": "AWS Lambda", "aws": "AWS",
    "ci/cd": "CI/CD", "rest": "REST API",
    "css3": "CSS", "html5": "HTML",
    "c++": "C++", "c#": "C#",
    "scikit": "scikit-learn", "sklearn": "scikit-learn",
    "tf2": "TensorFlow", "pt": "PyTorch",
    "oop": "OOP", "tdd": "TDD",
}

# ── Seniority inference ─────────────────────────────────────────────────
SENIORITY_MAP = [
    (r"\b(intern|trainee|fresher|entry.level)\b", "junior"),
    (r"\bjunior\b",                                "junior"),
    (r"\b(associate|mid.level|mid\s+level)\b",     "mid"),
    (r"\bsenior\b",                                "senior"),
    (r"\b(lead|tech lead|technical lead)\b",       "lead"),
    (r"\b(staff|principal|distinguished)\b",       "staff"),
    (r"\b(manager|head of|director|vp|cto|ceo)\b","manager"),
]

EXP_SENIORITY = [
    (0, 2,  "junior"),
    (2, 5,  "mid"),
    (5, 9,  "senior"),
    (9, 14, "lead"),
    (14, 99,"staff"),
]


def _infer_seniority(role: str, exp_years: float) -> str:
    role_lower = role.lower()
    for pattern, level in SENIORITY_MAP:
        if re.search(pattern, role_lower):
            return level
    for lo, hi, level in EXP_SENIORITY:
        if lo <= exp_years < hi:
            return level
    return "mid"


def _normalize_skill(skill: str) -> str:
    s = skill.strip().lower()
    return SKILL_ALIASES.get(s, skill.strip().title())


def _normalize_skills(skills: list[str]) -> list[str]:
    seen = set()
    result = []
    for sk in skills:
        norm = _normalize_skill(sk)
        key = norm.lower()
        if key not in seen:
            seen.add(key)
            result.append(norm)
    return result


def _fingerprint(profile: CandidateProfile) -> str:
    """Stable fingerprint for deduplication."""
    key = "|".join([
        profile.email.lower(),
        profile.name.lower(),
        profile.current_company.lower(),
        profile.source,
    ])
    return hashlib.md5(key.encode()).hexdigest()


class Normalizer:
    """
    Stateless normalizer. Pass in a CandidateProfile, get back
    an enriched version. LLM enrichment is optional and only
    triggered for resume_dir profiles with sparse structured data.
    """

    def __init__(self, llm_client=None):
        self.llm = llm_client  # Optional — if None, LLM enrichment is skipped

    def normalize(self, profile: CandidateProfile) -> CandidateProfile:
        """Normalize a single profile in-place and return it."""
        profile.skills      = _normalize_skills(profile.skills)
        profile.seniority   = _infer_seniority(
            profile.current_role, profile.total_experience_years
        )
        profile.fingerprint = _fingerprint(profile)
        profile.name        = profile.name.strip().title()
        profile.current_role    = profile.current_role.strip()
        profile.current_company = profile.current_company.strip()
        profile.location        = profile.location.strip()

        # LLM enrichment for resume-dir profiles where heuristics left gaps
        if (self.llm and profile.source == "resume_dir"
                and profile.raw_text
                and (not profile.current_role or not profile.skills)):
            self._llm_enrich(profile)

        return profile

    def normalize_all(self, profiles: list[CandidateProfile]) -> list[CandidateProfile]:
        results = []
        for p in profiles:
            try:
                results.append(self.normalize(p))
            except Exception as exc:
                logger.warning(f"Normalizer failed for {p.raw_id}: {exc}")
                results.append(p)  # Keep unnormalized rather than drop
        return results

    def _llm_enrich(self, profile: CandidateProfile):
        """Ask LLM to extract structured fields from raw resume text."""
        import json
        system = (
            "You are a resume parser. Extract structured data from the resume text. "
            "Return ONLY valid JSON, no markdown fences."
        )
        user = f"""Extract from this resume and return JSON:
{{
  "name": "full name",
  "current_role": "most recent job title",
  "current_company": "most recent employer",
  "total_experience_years": <number>,
  "skills": ["list of technical skills"],
  "location": "city, country",
  "highest_degree": "degree name",
  "email": "email if found"
}}

Resume text:
{profile.raw_text[:3000]}"""

        try:
            raw = self.llm.complete(system, user)
            cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
            data = json.loads(cleaned)
            if not profile.name        and data.get("name"):
                profile.name = data["name"]
            if not profile.current_role and data.get("current_role"):
                profile.current_role = data["current_role"]
            if not profile.current_company and data.get("current_company"):
                profile.current_company = data["current_company"]
            if not profile.skills and data.get("skills"):
                profile.skills = _normalize_skills(data["skills"])
            if not profile.location and data.get("location"):
                profile.location = data["location"]
            if not profile.highest_degree and data.get("highest_degree"):
                profile.highest_degree = data["highest_degree"]
            if not profile.email and data.get("email"):
                profile.email = data["email"]
            if not profile.total_experience_years and data.get("total_experience_years"):
                profile.total_experience_years = float(data["total_experience_years"])
            # Re-infer seniority with enriched data
            profile.seniority = _infer_seniority(
                profile.current_role, profile.total_experience_years
            )
        except Exception as exc:
            logger.warning(f"LLM enrichment failed for {profile.raw_id}: {exc}")
