"""
app.py
─────────────────────────────────────────────────────────────
TA Automation — Streamlit UI
Run:  streamlit run app.py
"""

from __future__ import annotations
import logging
import os
import sys
from pathlib import Path

import streamlit as st
import yaml

# ── Path fix for PyInstaller bundle ───────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
    os.chdir(BASE_DIR)
else:
    BASE_DIR = Path(__file__).parent

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
#  Config
# ══════════════════════════════════════════════════════════════════════════

@st.cache_resource
def load_config() -> dict:
    for candidate in ["config.local.yaml", "config.yaml"]:
        p = BASE_DIR / candidate
        if p.exists():
            with open(p) as f:
                return yaml.safe_load(f)
    st.error("No config.yaml found. Please create config.local.yaml.")
    st.stop()


# ══════════════════════════════════════════════════════════════════════════
#  Cached heavy objects  (created once per session)
# ══════════════════════════════════════════════════════════════════════════

@st.cache_resource
def get_llm_client():
    from llm_client import LLMClient
    return LLMClient(load_config())


@st.cache_resource
def get_source_manager():
    from connectors.source_manager import SourceManager
    return SourceManager(load_config())


@st.cache_resource
def get_scoring_engine():
    from scoring_engine import ScoringEngine
    return ScoringEngine(load_config())


@st.cache_resource
def get_normalizer():
    from normalizer import Normalizer
    return Normalizer(llm_client=get_llm_client())


# ══════════════════════════════════════════════════════════════════════════
#  Page config
# ══════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="TA Automation",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
.score-bar-wrap { background:#f0f0f0; border-radius:6px; height:10px; width:100%; }
.score-bar      { border-radius:6px; height:10px; }
.rank-badge     { font-size:22px; font-weight:700; color:#1a1a2e; }
.source-pill    { display:inline-block; padding:2px 10px; border-radius:12px;
                  font-size:12px; font-weight:600; margin-right:4px; }
.pill-naukri    { background:#fff3cd; color:#856404; }
.pill-linkedin  { background:#cfe2ff; color:#084298; }
.pill-resume    { background:#d1e7dd; color:#0a3622; }
.skill-chip     { display:inline-block; background:#e9ecef; border-radius:10px;
                  padding:2px 8px; font-size:12px; margin:2px; }
.skill-chip-miss{ display:inline-block; background:#f8d7da; border-radius:10px;
                  padding:2px 8px; font-size:12px; margin:2px; color:#842029; }
.metric-box     { background:#f8f9fa; border-radius:8px; padding:10px 14px;
                  text-align:center; border:1px solid #dee2e6; }
.metric-val     { font-size:26px; font-weight:700; color:#0d6efd; }
.metric-lbl     { font-size:12px; color:#6c757d; }
.section-header { font-size:18px; font-weight:600; margin-top:8px; margin-bottom:4px; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════
#  Sidebar
# ══════════════════════════════════════════════════════════════════════════

def render_sidebar(config: dict):
    with st.sidebar:
        st.title("🎯 TA Automation")
        st.caption(f"Recruiter: **{config.get('recruiter', {}).get('name', 'You')}**")
        st.divider()

        # Source status
        st.markdown("**Active sources**")
        sm = get_source_manager()
        status = sm.status_report()
        source_labels = {
            "naukri":     ("🟠 Naukri",     "pill-naukri"),
            "linkedin":   ("🔵 LinkedIn",   "pill-linkedin"),
            "resume_dir": ("🟢 Resume dir", "pill-resume"),
        }
        for key, info in status.items():
            label, _ = source_labels.get(key, (key, ""))
            icon = "✅" if info["enabled"] else "⬜"
            st.markdown(f"{icon} {label}")

        st.divider()

        # LLM info
        llm_cfg = config.get("llm", {})
        provider = llm_cfg.get("provider", "openai")
        model = llm_cfg.get(provider, {}).get("model", "—")
        st.markdown(f"**LLM** `{provider}` / `{model}`")

        st.divider()

        # Index management
        st.markdown("**Candidate index**")
        engine = get_scoring_engine()
        count  = engine.collection_count()
        st.metric("Indexed candidates", count)
        if st.button("🗑 Clear index", use_container_width=True):
            engine.clear_index()
            st.success("Index cleared.")
            st.rerun()

        st.divider()
        st.caption("Logs appear in the terminal where you launched this app.")


# ══════════════════════════════════════════════════════════════════════════
#  Score bar helper
# ══════════════════════════════════════════════════════════════════════════

def score_bar(value: float, color: str = "#0d6efd") -> str:
    pct = int(value * 100)
    return (
        f'<div class="score-bar-wrap">'
        f'<div class="score-bar" style="width:{pct}%;background:{color};"></div>'
        f'</div><small style="color:#6c757d">{pct}%</small>'
    )


def source_pill(source: str) -> str:
    mapping = {
        "naukri":     ("Naukri",     "pill-naukri"),
        "linkedin":   ("LinkedIn",   "pill-linkedin"),
        "resume_dir": ("Resume dir", "pill-resume"),
    }
    label, cls = mapping.get(source, (source, ""))
    return f'<span class="source-pill {cls}">{label}</span>'


# ══════════════════════════════════════════════════════════════════════════
#  Candidate card
# ══════════════════════════════════════════════════════════════════════════

def render_candidate_card(rank: int, sc, show_details: bool = False):
    from scoring_engine import ScoredCandidate
    p = sc.profile

    with st.container():
        col_rank, col_info, col_scores = st.columns([1, 5, 4])

        with col_rank:
            color = ["🥇", "🥈", "🥉"][rank - 1] if rank <= 3 else f"**#{rank}**"
            st.markdown(
                f'<div class="rank-badge" style="text-align:center;padding-top:10px;">'
                f'{color}</div>', unsafe_allow_html=True
            )
            st.markdown(
                f'<div style="text-align:center;font-size:28px;font-weight:700;'
                f'color:#0d6efd">{sc.score_pct}%</div>', unsafe_allow_html=True
            )

        with col_info:
            st.markdown(
                f"**{p.name or 'Unknown'}** "
                + source_pill(p.source),
                unsafe_allow_html=True,
            )
            st.caption(
                f"{'📌 ' + p.current_role if p.current_role else ''}"
                + (f"  @  {p.current_company}" if p.current_company else "")
            )
            st.caption(
                f"🗓 {p.total_experience_years:.0f} yrs exp  "
                f"| 📍 {p.location or '—'}  "
                f"| 🎖 {p.seniority or '—'}"
            )

            if sc.matched_skills:
                chips = "".join(
                    f'<span class="skill-chip">✓ {s}</span>'
                    for s in sc.matched_skills[:8]
                )
                st.markdown(chips, unsafe_allow_html=True)
            if sc.missing_skills:
                chips = "".join(
                    f'<span class="skill-chip-miss">✗ {s}</span>'
                    for s in sc.missing_skills[:5]
                )
                st.markdown(chips, unsafe_allow_html=True)

            if sc.llm_summary:
                st.info(f"💬 {sc.llm_summary}")

        with col_scores:
            metrics = [
                ("Semantic match",     sc.skill_match_score,   "#0d6efd"),
                ("Skills coverage",    sc.required_coverage,   "#198754"),
                ("Experience fit",     sc.experience_score,    "#fd7e14"),
                ("Seniority match",    sc.seniority_score,     "#6f42c1"),
                ("Profile recency",    sc.recency_score,       "#20c997"),
            ]
            for label, val, color in metrics:
                st.markdown(
                    f"<small>{label}</small>" + score_bar(val, color),
                    unsafe_allow_html=True,
                )

        # Expandable detail
        if p.profile_url:
            st.markdown(f"[🔗 Open profile]({p.profile_url})", unsafe_allow_html=True)

        with st.expander("More details", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Email:** {p.email or '—'}")
                st.markdown(f"**Phone:** {p.phone or '—'}")
                st.markdown(f"**Degree:** {p.highest_degree or '—'}")
                st.markdown(f"**Notice period:** "
                            f"{'%d days' % p.notice_period_days if p.notice_period_days else '—'}")
            with c2:
                all_skills = ", ".join(p.skills) if p.skills else "—"
                st.markdown(f"**All skills:** {all_skills}")
                st.markdown(f"**Source ID:** `{p.raw_id[:20]}…`")
                if p.last_updated:
                    st.markdown(f"**Last updated:** {p.last_updated.strftime('%d %b %Y')}")

        st.divider()


# ══════════════════════════════════════════════════════════════════════════
#  Main page
# ══════════════════════════════════════════════════════════════════════════

def main():
    config = load_config()
    render_sidebar(config)

    st.header("Find top candidates for a role")

    # ── JD Input ──────────────────────────────────────────────────────────
    tab_jd, tab_settings = st.tabs(["🔍 Search", "⚙️ Settings"])

    with tab_jd:
        col_jd, col_opts = st.columns([3, 1])

        with col_jd:
            jd_text = st.text_area(
                "Paste the Job Description here",
                height=220,
                placeholder=(
                    "e.g. We are looking for a Senior Python Engineer with 5+ years "
                    "of experience in FastAPI, PostgreSQL, and AWS…"
                ),
            )

        with col_opts:
            location = st.text_input("Location filter", placeholder="Bengaluru, India")
            max_per_source = st.slider("Results per source", 10, 100, 50, step=10)
            top_k = st.slider("Top N to show", 5, 20, 10, step=1)
            generate_summaries = st.checkbox("Generate AI summaries", value=True)

        search_btn = st.button("🚀 Find top candidates", type="primary", use_container_width=True)

        # ── Results ────────────────────────────────────────────────────────
        if search_btn:
            if not jd_text.strip():
                st.warning("Please paste a Job Description to search.")
            else:
                _run_search(jd_text, location, max_per_source, top_k, generate_summaries)

    with tab_settings:
        render_settings(config)


def _run_search(jd_text, location, max_per_source, top_k, generate_summaries):
    llm     = get_llm_client()
    sm      = get_source_manager()
    engine  = get_scoring_engine()
    norm    = get_normalizer()

    # Step 1: Parse JD
    with st.status("Parsing job description…", expanded=True) as status:
        st.write("Extracting requirements with LLM…")
        try:
            jd_parsed = llm.parse_jd(jd_text)
        except Exception as e:
            st.error(f"JD parsing failed: {e}")
            return
        st.write(f"✅ Role: **{jd_parsed.get('role_title', 'N/A')}**  "
                 f"| Seniority: **{jd_parsed.get('seniority', 'N/A')}**  "
                 f"| Min exp: **{jd_parsed.get('min_experience_years', '?')} yrs**")
        req_skills = jd_parsed.get("required_skills", [])
        st.write(f"Required skills: {', '.join(req_skills[:10])}")

        # Step 2: Fetch candidates
        st.write("Fetching candidates from active sources…")
        query = jd_parsed.get("role_title", "") + " " + " ".join(req_skills[:5])
        candidates, summary = sm.fetch_all(
            query=query, location=location, max_per_source=max_per_source
        )

        if summary.errors:
            for err in summary.errors:
                st.warning(f"⚠️ {err}")

        if summary.total == 0:
            status.update(label="No candidates found.", state="error")
            st.error(
                "No candidates returned. Check that at least one source is "
                "enabled and configured in config.local.yaml."
            )
            return

        st.write(
            f"✅ Retrieved **{summary.total}** candidates from: "
            + ", ".join(summary.active_sources)
        )

        # Step 3: Normalize
        st.write("Normalising profiles…")
        candidates = norm.normalize_all(candidates)

        # Step 4: Index + Score
        st.write("Indexing and scoring…")
        engine.index_candidates(candidates)
        results = engine.rank(jd_parsed, candidates, top_k=top_k)

        # Step 5: LLM summaries
        if generate_summaries and results:
            st.write("Generating AI summaries for top candidates…")
            for sc in results:
                try:
                    sc.llm_summary = llm.summarize_candidate(
                        {"name": sc.profile.name,
                         "current_role": sc.profile.current_role,
                         "total_experience_years": sc.profile.total_experience_years,
                         "skills": sc.profile.skills,
                         "source": sc.profile.source},
                        jd_parsed,
                    )
                except Exception:
                    sc.llm_summary = ""

        status.update(label="Done!", state="complete", expanded=False)

    # ── Summary metrics ───────────────────────────────────────────────────
    st.markdown("### Results")
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(
            f'<div class="metric-box"><div class="metric-val">{summary.total}</div>'
            f'<div class="metric-lbl">Total candidates</div></div>',
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f'<div class="metric-box"><div class="metric-val">{summary.naukri}</div>'
            f'<div class="metric-lbl">From Naukri</div></div>',
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f'<div class="metric-box"><div class="metric-val">{summary.linkedin}</div>'
            f'<div class="metric-lbl">From LinkedIn</div></div>',
            unsafe_allow_html=True,
        )
    with m4:
        st.markdown(
            f'<div class="metric-box"><div class="metric-val">{summary.resume_dir}</div>'
            f'<div class="metric-lbl">From resumes</div></div>',
            unsafe_allow_html=True,
        )
    with m5:
        top_score = f"{results[0].score_pct}%" if results else "—"
        st.markdown(
            f'<div class="metric-box"><div class="metric-val">{top_score}</div>'
            f'<div class="metric-lbl">Top match score</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── JD summary sidebar ────────────────────────────────────────────────
    with st.expander("📋 Parsed JD summary", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Role:** {jd_parsed.get('role_title', '—')}")
            st.markdown(f"**Seniority:** {jd_parsed.get('seniority', '—')}")
            st.markdown(f"**Min experience:** {jd_parsed.get('min_experience_years', '—')} years")
            st.markdown(f"**Required skills:** {', '.join(jd_parsed.get('required_skills', []))}")
        with c2:
            st.markdown(f"**Nice to have:** {', '.join(jd_parsed.get('nice_to_have', []))}")
            st.markdown(f"**Domain:** {', '.join(jd_parsed.get('domain_keywords', []))}")

    # ── Candidate cards ───────────────────────────────────────────────────
    if not results:
        st.warning("No candidates scored. Try broadening the JD or enabling more sources.")
    else:
        st.markdown(f"### Top {len(results)} candidates")
        for i, sc in enumerate(results, 1):
            render_candidate_card(i, sc)

        # Export
        st.markdown("---")
        if st.button("📥 Export results as CSV"):
            import csv, io
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=[
                "rank", "name", "source", "score_pct", "current_role",
                "current_company", "experience_years", "seniority",
                "location", "matched_skills", "missing_skills",
                "email", "phone", "profile_url", "llm_summary",
            ])
            writer.writeheader()
            for i, sc in enumerate(results, 1):
                p = sc.profile
                writer.writerow({
                    "rank": i,
                    "name": p.name,
                    "source": p.source,
                    "score_pct": sc.score_pct,
                    "current_role": p.current_role,
                    "current_company": p.current_company,
                    "experience_years": p.total_experience_years,
                    "seniority": p.seniority,
                    "location": p.location,
                    "matched_skills": "; ".join(sc.matched_skills),
                    "missing_skills": "; ".join(sc.missing_skills),
                    "email": p.email,
                    "phone": p.phone,
                    "profile_url": p.profile_url,
                    "llm_summary": sc.llm_summary,
                })
            st.download_button(
                "Download CSV",
                data=buf.getvalue(),
                file_name="top_candidates.csv",
                mime="text/csv",
            )


def render_settings(config: dict):
    st.markdown("### Configuration")
    st.info(
        "Edit `config.local.yaml` in the app folder to change settings. "
        "Restart the app after saving."
    )
    st.markdown("#### Source status")
    sm = get_source_manager()
    for name, info in sm.status_report().items():
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{name}** — `{info['type']}`")
        with col2:
            st.markdown("✅ Enabled" if info["enabled"] else "⬜ Disabled")

    st.markdown("#### Scoring weights")
    scoring = config.get("scoring", {})
    weights = {
        "Semantic skill match": scoring.get("semantic_skill_match", 0.40),
        "Required skills coverage": scoring.get("required_skills_coverage", 0.25),
        "Experience fit": scoring.get("experience_fit", 0.20),
        "Seniority match": scoring.get("seniority_match", 0.10),
        "Profile recency": scoring.get("profile_recency", 0.05),
    }
    for label, w in weights.items():
        c1, c2 = st.columns([3, 1])
        with c1:
            st.progress(w, text=label)
        with c2:
            st.markdown(f"**{int(w*100)}%**")

    st.markdown("#### LLM")
    llm_cfg = config.get("llm", {})
    provider = llm_cfg.get("provider", "openai")
    pcfg = llm_cfg.get(provider, {})
    st.markdown(f"Provider: `{provider}`")
    st.markdown(f"Model: `{pcfg.get('model', '—')}`")
    st.markdown(f"Base URL: `{pcfg.get('base_url', '—')}`")


# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()
