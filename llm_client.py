"""
llm_client.py
─────────────────────────────────────────────────────────────
Single OpenAI-compatible LLM client that works with:
  • OpenAI API   (provider: openai)
  • Ollama       (provider: ollama) — exposes OpenAI-compatible /v1 endpoint

Switch providers in config.local.yaml — zero code changes needed.
"""

from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from typing import Optional

import yaml
from openai import OpenAI

logger = logging.getLogger(__name__)


def load_config(path: Optional[str] = None) -> dict:
    candidates = [path] if path else ["config.local.yaml", "config.yaml"]
    for p in candidates:
        if p and Path(p).exists():
            with open(p) as f:
                return yaml.safe_load(f)
    raise FileNotFoundError("No config.yaml found. Create config.local.yaml first.")


class LLMClient:
    """
    Thin wrapper around the OpenAI SDK.
    Ollama serves an OpenAI-compatible API at /v1, so the same client
    works for both — only base_url and model differ.
    """

    def __init__(self, config: Optional[dict] = None):
        cfg = config or load_config()
        llm_cfg  = cfg["llm"]
        provider = llm_cfg["provider"]          # "openai" | "ollama"
        pcfg     = llm_cfg[provider]

        self.model       = pcfg["model"]
        self.temperature = pcfg.get("temperature", 0.2)
        self.max_tokens  = pcfg.get("max_tokens", 1000)
        self.provider    = provider

        self.client = OpenAI(
            api_key  = pcfg["api_key"],
            base_url = pcfg["base_url"],
        )
        logger.info(f"LLM: provider={provider}  model={self.model}")

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Single-turn chat completion. Returns assistant text."""
        response = self.client.chat.completions.create(
            model       = self.model,
            temperature = self.temperature,
            max_tokens  = self.max_tokens,
            messages    = [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
        )
        return response.choices[0].message.content.strip()

    def parse_jd(self, jd_text: str) -> dict:
        """Extract structured requirements from a raw Job Description."""
        system = (
            "You are a talent acquisition specialist. Extract structured data "
            "from job descriptions. Return ONLY valid JSON, no markdown fences."
        )
        user = f"""Extract the following from this job description and return as JSON:
{{
  "required_skills": ["must-have technical skills"],
  "nice_to_have": ["preferred but optional skills"],
  "min_experience_years": <integer>,
  "seniority": "junior | mid | senior | lead | staff",
  "domain_keywords": ["domain or industry keywords"],
  "role_title": "normalized job title"
}}

Job Description:
{jd_text}"""

        raw = self.complete(system, user)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(cleaned)

    def summarize_candidate(self, profile: dict, jd_parsed: dict) -> str:
        """One-line recruiter summary for a candidate vs a specific JD."""
        system = (
            "You are a senior recruiter. Write ONE concise sentence (max 25 words) "
            "summarizing why this candidate is or isn't a strong fit for the role. "
            "Be specific — mention the most relevant skill or gap."
        )
        user = f"""Candidate:
- Name: {profile.get('name', 'Unknown')}
- Role: {profile.get('current_role', 'N/A')}
- Experience: {profile.get('total_experience_years', '?')} years
- Skills: {', '.join(profile.get('skills', [])[:8])}
- Source: {profile.get('source', 'N/A')}

Role needs: {', '.join(jd_parsed.get('required_skills', [])[:6])}
Seniority: {jd_parsed.get('seniority', 'N/A')}"""

        return self.complete(system, user)


# ── Smoke test:  python llm_client.py ─────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = LLMClient()

    sample_jd = """
    Senior Python Engineer, 5+ years. Must have: FastAPI, PostgreSQL, Docker, AWS.
    Nice to have: Kubernetes, Terraform. Domain: FinTech / payments.
    """
    print("\n── JD parse ──")
    parsed = client.parse_jd(sample_jd)
    print(json.dumps(parsed, indent=2))

    print("\n── Candidate summary ──")
    sample = {
        "name": "Priya Sharma",
        "current_role": "Python Developer",
        "total_experience_years": 4,
        "skills": ["Python", "FastAPI", "MySQL", "Docker", "AWS EC2"],
        "source": "Naukri",
    }
    print(client.summarize_candidate(sample, parsed))
