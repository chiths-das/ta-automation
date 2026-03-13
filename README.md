# TA Automation — Local Recruiter Tool

Multi-source candidate sourcing and ranking that runs entirely on your laptop.
Paste a Job Description, get your **top 10 candidates ranked by AI** — sourced from
Naukri, LinkedIn, and/or a local/OneDrive/Google Drive resume folder.

---

## What it does

```
Job Description  →  Naukri API  ─┐
                 →  LinkedIn API ─┼→ Normalize → Score → Top 10
                 →  Resume folder ┘
```

1. **Parses the JD** with an LLM (OpenAI or self-hosted Ollama) to extract required skills, seniority, and experience
2. **Fetches candidates** from whichever sources you have configured
3. **Normalizes** all profiles into a single schema and deduplicates across sources
4. **Scores** every candidate on 5 signals (semantic match, skill coverage, experience fit, seniority, recency)
5. **Displays** the top 10 with match scores, skill gaps, and an AI-generated one-liner per candidate

---

## Quick start (Python — developer setup)

### 1 — Install dependencies

```bash
pip install -r requirements.txt
```

### 2 — Create your local config

```bash
cp config.yaml config.local.yaml
```

Open `config.local.yaml` and fill in your details (see **Configuration** below).
`config.local.yaml` is in `.gitignore` and is never shared.

### 3 — Run

```bash
streamlit run app.py
```

The browser opens automatically at `http://localhost:8501`.

---

## Quick start (pre-built binary — recruiter setup)

> No Python required. Share the zip from your team's IT person.

**Windows**
1. Unzip the `ta_automation` folder anywhere
2. Double-click **`run.bat`**
3. On first run it creates `config.local.yaml` and opens it in Notepad — fill in your keys, save, then run again

**Mac / Linux**
1. Unzip the `ta_automation` folder
2. Open Terminal in that folder and run:
   ```bash
   bash run.sh
   ```
3. Same first-run config flow as Windows

The app opens at `http://localhost:8501` automatically.

---

## Configuration (`config.local.yaml`)

### LLM backend

```yaml
llm:
  provider: "openai"       # switch to "ollama" when ready — zero code changes

  openai:
    api_key: "sk-..."      # your OpenAI key
    model: "gpt-4o"

  ollama:
    base_url: "http://192.168.1.50:11434/v1"   # LAN IP of your Ollama server
    model: "llama3.1:8b"
```

Change `provider:` between `"openai"` and `"ollama"` to switch. Everything else stays the same.

---

### Sources — any combination works

The app runs fine with **one, two, or all three** sources enabled.
If a source is misconfigured or unreachable, it is silently skipped and the others continue.

#### Naukri

```yaml
naukri:
  enabled: true
  api_key: "naukri-api-key-here"
  client_id: "your-naukri-client-id"
  client_secret: "your-naukri-client-secret"
```

Requires official Naukri Recruiter API access. Set `enabled: false` if you don't have it.

#### LinkedIn

```yaml
linkedin:
  enabled: true
  client_id: "your-linkedin-client-id"
  client_secret: "your-linkedin-client-secret"
  access_token: "your-linkedin-access-token"
```

Requires LinkedIn Recruiter API (enterprise/partner access). Set `enabled: false` if not available.

#### Resume folder — local, OneDrive, or Google Drive

```yaml
resume_directory:
  enabled: true
  path: "./resumes"           # change to your actual folder path
  formats: ["pdf", "docx", "doc"]
```

**Supported path types:**

| Location | Windows path example | Mac path example |
|---|---|---|
| Local folder | `C:/Resumes` | `/Users/name/Resumes` |
| OneDrive | `C:/Users/name/OneDrive/Resumes` | `/Users/name/OneDrive - Company/Resumes` |
| Google Drive | `G:/My Drive/Resumes` | `/Volumes/GoogleDrive/My Drive/Resumes` |
| Network share / NAS | `\\server\share\Resumes` | `/Volumes/NAS/Resumes` |

OneDrive and Google Drive must be **running and the folder synced** before launching the app.
If the path doesn't exist at startup, the source is skipped with a warning — the app keeps running.

---

### Scoring weights

```yaml
scoring:
  semantic_skill_match: 0.40      # Embedding cosine similarity
  required_skills_coverage: 0.25  # % of required skills matched exactly
  experience_fit: 0.20            # Gaussian fit around ideal years
  seniority_match: 0.10           # junior/mid/senior/lead alignment
  profile_recency: 0.05           # How recently the profile was updated
  top_n_results: 10
```

Weights must sum to 1.0. Adjust to match your team's priorities.

---

## Switching from OpenAI to Ollama

1. Install [Ollama](https://ollama.com) on one machine on your LAN
2. Pull a model:
   ```bash
   ollama pull llama3.1:8b
   ```
3. In `config.local.yaml`:
   ```yaml
   llm:
     provider: "ollama"
     ollama:
       base_url: "http://<LAN-IP>:11434/v1"
       model: "llama3.1:8b"
   ```
4. Restart the app — no code changes needed

---

## File structure

```
ta_automation/
├── app.py                    # Streamlit UI (entry point)
├── llm_client.py             # OpenAI-compatible LLM wrapper
├── normalizer.py             # Profile normalization + LLM enrichment
├── scoring_engine.py         # ChromaDB vector search + ranking
├── config.yaml               # Template config (safe to commit)
├── config.local.yaml         # Your keys — never commit this ← create this
├── requirements.txt
├── build.py                  # Build distribution package
├── ta_automation.spec        # PyInstaller spec
├── run.bat                   # Windows launcher
├── run.sh                    # Mac/Linux launcher
├── .gitignore
└── connectors/
    ├── __init__.py
    ├── base_connector.py     # Abstract base — resilience logic lives here
    ├── naukri_connector.py
    ├── linkedin_connector.py
    ├── resume_connector.py   # PDF/DOCX parser + OneDrive/GDrive support
    └── source_manager.py     # Orchestrates all sources, deduplication
```

---

## Building a distribution package

Run this on the developer machine once:

```bash
python build.py
```

This produces `dist/ta_automation/` — a self-contained folder with no Python dependency.
Zip it and share with recruiters. They just unzip and run `run.bat` or `run.sh`.

```bash
# Optional: clean build artefacts first
python build.py --clean
```

---

## Troubleshooting

**"No candidates found"**
Open the terminal where you launched the app. Source status is logged at startup:
```
── Source status ──────────────────────────
  naukri          ✓ enabled
  linkedin        ✗ skipped  ← look for the reason here
  resume_dir      ✓ enabled
───────────────────────────────────────────
```
If a source shows `✗ skipped`, the reason is in the line above it.

**OneDrive / Google Drive folder not found**
- Windows: make sure OneDrive or Drive for Desktop is running and shows a green tick
- Mac: the Google Drive volume appears under `/Volumes/` only when the app is open
- Try the path in File Explorer / Finder first before pasting into config

**LLM call failing**
- OpenAI: check your `api_key` in `config.local.yaml`
- Ollama: confirm the server is reachable — `curl http://<LAN-IP>:11434/api/tags` should return JSON
- Both: run `python llm_client.py` for a quick smoke test

**Slow first run**
The embedding model (`all-MiniLM-L6-v2`, ~90 MB) downloads on first use and is cached locally.
Subsequent runs are fast.

**PyInstaller binary won't start (Mac)**
```bash
chmod +x ta_automation
xattr -cr ta_automation   # remove quarantine flag from downloaded binary
```

---

## Data privacy

- Candidate data **never leaves your machine** (all stored in `./data/chroma` locally)
- The only outbound calls are to the LLM endpoint (OpenAI API or your own Ollama server)
- The LLM receives the JD text and short candidate snippets for parsing/summarization — no bulk PII is sent
- Switch to Ollama to eliminate all external API calls entirely

---

## Requirements

| Component | Minimum |
|---|---|
| Python | 3.10+ (dev setup only) |
| RAM | 4 GB (8 GB recommended for local embeddings) |
| Disk | ~500 MB (model cache + ChromaDB) |
| OpenAI key | Required if `provider: openai` |
| Ollama server | Required if `provider: ollama` |
| Naukri API access | Required if `naukri.enabled: true` |
| LinkedIn Recruiter API | Required if `linkedin.enabled: true` |
