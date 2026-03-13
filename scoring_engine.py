"""
scoring_engine.py
─────────────────────────────────────────────────────────────
Scores and ranks candidates against a parsed Job Description.

Pipeline:
  1. Embed the JD and all candidate profiles using sentence-transformers
  2. ANN search via ChromaDB to retrieve top-N semantically similar candidates
  3. Apply weighted multi-signal scoring to re-rank
  4. Return top-K ScoredCandidate objects with per-signal breakdown
"""

from __future__ import annotations
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from connectors.base_connector import CandidateProfile

logger = logging.getLogger(__name__)


@dataclass
class ScoredCandidate:
    profile: CandidateProfile
    total_score: float                       # 0.0 – 1.0
    skill_match_score: float = 0.0          # semantic similarity
    required_coverage: float = 0.0          # fraction of required skills matched
    experience_score: float = 0.0
    seniority_score: float = 0.0
    recency_score: float = 0.0
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    llm_summary: str = ""                   # filled in by caller if desired

    @property
    def score_pct(self) -> int:
        return round(self.total_score * 100)


class ScoringEngine:
    """
    Wraps ChromaDB + sentence-transformers.
    All heavy imports are deferred so the module loads fast
    even if deps aren't installed yet.
    """

    def __init__(self, config: dict):
        self.config = config
        vdb_cfg = config.get("vector_db", {})
        scoring_cfg = config.get("scoring", {})

        self.persist_dir   = vdb_cfg.get("persist_directory", "./data/chroma")
        self.collection_nm = vdb_cfg.get("collection_name", "candidates")
        self.embed_model   = vdb_cfg.get("embedding_model", "all-MiniLM-L6-v2")

        self.weights = {
            "semantic":   scoring_cfg.get("semantic_skill_match",     0.40),
            "coverage":   scoring_cfg.get("required_skills_coverage", 0.25),
            "experience": scoring_cfg.get("experience_fit",           0.20),
            "seniority":  scoring_cfg.get("seniority_match",         0.10),
            "recency":    scoring_cfg.get("profile_recency",         0.05),
        }
        self.top_n = scoring_cfg.get("top_n_results", 10)

        self._embedder = None
        self._chroma   = None
        self._collection = None

    # ── Lazy init ──────────────────────────────────────────────────────────

    def _get_embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.embed_model}")
            self._embedder = SentenceTransformer(self.embed_model)
        return self._embedder

    def _get_collection(self):
        if self._collection is None:
            import chromadb
            Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
            self._chroma = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = self._chroma.get_or_create_collection(
                name=self.collection_nm,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    # ── Indexing ───────────────────────────────────────────────────────────

    def index_candidates(self, profiles: list[CandidateProfile]) -> int:
        """
        Upsert candidate profiles into ChromaDB.
        Returns number of profiles indexed.
        """
        if not profiles:
            return 0

        embedder   = self._get_embedder()
        collection = self._get_collection()

        texts, ids, metadatas = [], [], []
        for p in profiles:
            text = self._profile_to_text(p)
            texts.append(text)
            ids.append(p.fingerprint or p.raw_id)
            metadatas.append(self._profile_to_metadata(p))

        logger.info(f"Embedding {len(texts)} candidate profiles…")
        embeddings = embedder.encode(texts, show_progress_bar=False).tolist()

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info(f"Indexed {len(profiles)} candidates into ChromaDB.")
        return len(profiles)

    def clear_index(self):
        """Wipe and recreate the collection (force reindex)."""
        if self._chroma:
            self._chroma.delete_collection(self.collection_nm)
            self._collection = None
        logger.info("ChromaDB collection cleared.")

    def collection_count(self) -> int:
        try:
            return self._get_collection().count()
        except Exception:
            return 0

    # ── Scoring ────────────────────────────────────────────────────────────

    def rank(
        self,
        jd_parsed: dict,
        candidates: list[CandidateProfile],
        top_k: Optional[int] = None,
    ) -> list[ScoredCandidate]:
        """
        Score and rank candidates against a parsed JD.
        If candidates is non-empty, scores them directly (no ChromaDB lookup).
        Pass candidates=[] to query from the persistent index.
        """
        top_k = top_k or self.top_n

        if candidates:
            pool = candidates
        else:
            pool = self._query_index(jd_parsed, n_results=min(top_k * 5, 200))

        if not pool:
            logger.warning("No candidates to score.")
            return []

        jd_text = self._jd_to_text(jd_parsed)
        embedder = self._get_embedder()
        jd_embedding = embedder.encode([jd_text], show_progress_bar=False)[0]

        profile_texts = [self._profile_to_text(p) for p in pool]
        profile_embeddings = embedder.encode(
            profile_texts, show_progress_bar=False
        )

        scored = []
        for profile, emb in zip(pool, profile_embeddings):
            sc = self._score(profile, emb, jd_embedding, jd_parsed)
            scored.append(sc)

        scored.sort(key=lambda x: x.total_score, reverse=True)
        return scored[:top_k]

    def _score(
        self,
        profile: CandidateProfile,
        profile_emb,
        jd_emb,
        jd_parsed: dict,
    ) -> ScoredCandidate:
        import numpy as np

        # 1. Semantic similarity
        cosine = float(np.dot(profile_emb, jd_emb) / (
            np.linalg.norm(profile_emb) * np.linalg.norm(jd_emb) + 1e-9
        ))
        semantic = max(0.0, min(1.0, (cosine + 1) / 2))

        # 2. Required skills coverage
        required = {s.lower() for s in jd_parsed.get("required_skills", [])}
        candidate_skills = {s.lower() for s in profile.skills}
        matched = required & candidate_skills
        missing = required - candidate_skills
        coverage = len(matched) / max(len(required), 1)

        # 3. Experience fit (Gaussian centered on min_exp + 2)
        min_exp = float(jd_parsed.get("min_experience_years", 3))
        ideal   = min_exp + 2
        exp     = profile.total_experience_years
        exp_score = math.exp(-0.5 * ((exp - ideal) / max(ideal * 0.4, 1)) ** 2)

        # 4. Seniority match
        jd_seniority  = jd_parsed.get("seniority", "mid").lower()
        can_seniority = (profile.seniority or "").lower()
        seniority_score = 1.0 if jd_seniority == can_seniority else (
            0.6 if abs(
                _SENIORITY_RANK.get(jd_seniority, 2) -
                _SENIORITY_RANK.get(can_seniority, 2)
            ) == 1 else 0.2
        )

        # 5. Profile recency (decay over 2 years)
        recency = 0.5
        if profile.last_updated:
            now = datetime.now(timezone.utc)
            lu  = profile.last_updated
            if lu.tzinfo is None:
                lu = lu.replace(tzinfo=timezone.utc)
            days_old = (now - lu).days
            recency  = math.exp(-days_old / 730)

        total = (
            self.weights["semantic"]   * semantic
            + self.weights["coverage"]   * coverage
            + self.weights["experience"] * exp_score
            + self.weights["seniority"]  * seniority_score
            + self.weights["recency"]    * recency
        )

        return ScoredCandidate(
            profile=profile,
            total_score=round(total, 4),
            skill_match_score=round(semantic, 4),
            required_coverage=round(coverage, 4),
            experience_score=round(exp_score, 4),
            seniority_score=round(seniority_score, 4),
            recency_score=round(recency, 4),
            matched_skills=sorted(matched),
            missing_skills=sorted(missing),
        )

    # ── ChromaDB query ────────────────────────────────────────────────────

    def _query_index(self, jd_parsed: dict, n_results: int) -> list[CandidateProfile]:
        """Query ChromaDB for semantically similar candidates."""
        embedder   = self._get_embedder()
        collection = self._get_collection()

        if collection.count() == 0:
            logger.warning("ChromaDB collection is empty.")
            return []

        jd_text = self._jd_to_text(jd_parsed)
        jd_emb  = embedder.encode([jd_text], show_progress_bar=False).tolist()

        results = collection.query(
            query_embeddings=jd_emb,
            n_results=min(n_results, collection.count()),
            include=["metadatas", "documents"],
        )
        profiles = []
        for meta, doc in zip(
            results["metadatas"][0], results["documents"][0]
        ):
            profiles.append(self._metadata_to_profile(meta, doc))
        return profiles

    # ── Serialization helpers ─────────────────────────────────────────────

    def _profile_to_text(self, p: CandidateProfile) -> str:
        parts = [
            p.current_role,
            p.current_company,
            f"{p.total_experience_years} years experience",
            "Skills: " + ", ".join(p.skills),
            p.location,
            p.raw_text[:500] if p.raw_text else "",
        ]
        return " | ".join(x for x in parts if x)

    def _jd_to_text(self, jd: dict) -> str:
        parts = [
            jd.get("role_title", ""),
            "Required: " + ", ".join(jd.get("required_skills", [])),
            "Nice to have: " + ", ".join(jd.get("nice_to_have", [])),
            f"Seniority: {jd.get('seniority', '')}",
            f"Min experience: {jd.get('min_experience_years', 0)} years",
            " ".join(jd.get("domain_keywords", [])),
        ]
        return " | ".join(x for x in parts if x)

    def _profile_to_metadata(self, p: CandidateProfile) -> dict:
        return {
            "raw_id":               p.raw_id,
            "source":               p.source,
            "name":                 p.name,
            "email":                p.email,
            "phone":                p.phone,
            "current_role":         p.current_role,
            "current_company":      p.current_company,
            "total_experience_years": p.total_experience_years,
            "seniority":            p.seniority,
            "skills":               ",".join(p.skills),
            "location":             p.location,
            "profile_url":          p.profile_url,
            "fingerprint":          p.fingerprint,
            "last_updated":         p.last_updated.isoformat() if p.last_updated else "",
        }

    def _metadata_to_profile(self, meta: dict, doc: str) -> CandidateProfile:
        from datetime import datetime
        lu = None
        if meta.get("last_updated"):
            try:
                lu = datetime.fromisoformat(meta["last_updated"])
            except ValueError:
                pass
        return CandidateProfile(
            raw_id=meta.get("raw_id", ""),
            source=meta.get("source", ""),
            name=meta.get("name", ""),
            email=meta.get("email", ""),
            phone=meta.get("phone", ""),
            current_role=meta.get("current_role", ""),
            current_company=meta.get("current_company", ""),
            total_experience_years=float(meta.get("total_experience_years", 0)),
            seniority=meta.get("seniority", ""),
            skills=[s for s in meta.get("skills", "").split(",") if s],
            location=meta.get("location", ""),
            profile_url=meta.get("profile_url", ""),
            fingerprint=meta.get("fingerprint", ""),
            last_updated=lu,
            raw_text=doc,
        )


_SENIORITY_RANK = {
    "junior": 0, "mid": 1, "senior": 2,
    "lead": 3, "staff": 4, "manager": 5,
}
