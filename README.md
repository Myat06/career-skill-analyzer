# PresConsult AI

An AI-assisted career-readiness consultation tool built for a university
Internship & Career Center. It combines a student's academic record and
self-logged activities/achievements with an AI-graded resume review and a
skill-gap analysis against Indonesia's national **SKKNI** competency
standards, then turns all of it into consultation deliverables a career
advisor can actually hand to a student: a chat-based consultation session, a
multi-section PDF report, and a shareable one-page poster.

## What it does

- **Resume evaluation** — a student's resume is graded against a real
  7-category university rubric (contact info, education, experience,
  projects, skills, language, personal summary) by a local LLM, with every
  score backed by a verbatim quote pulled from the resume text and validated
  against it before being accepted.
- **Skill-gap analysis** — for a chosen job role, completed courses are
  checked against a curated SKKNI-competency-to-curriculum mapping, and
  resume/activity text is judged against each competency unit's real
  elements (again with quote-verified evidence, not free-form LLM opinion).
  The result is a per-unit match breakdown (matched / partial / missing),
  plus recommended courses to close each gap.
- **Consultation chat** — a chat interface grounded in the student's actual
  profile, resume score, and skill-gap results, with a fallback to general
  career guidance (and verified links to roadmap.sh) for roles outside the
  curated catalog.
- **Report & poster generation** — a full consultation PDF and a shareable
  PNG poster, built from the resume score, skill-gap analysis, and academic/
  activity evidence, with AI-written narrative sections (executive summary,
  roadmap, direction, coach message).
- **Persistent chat history** — consultation sessions are saved per student
  and can be reopened and continued later.

## Tech stack

**Backend:** FastAPI, PostgreSQL (async SQLAlchemy) with the `pgvector`
extension for embeddings, [Ollama](https://ollama.com) running locally for
both chat (`qwen3.5:9b`) and embeddings (`embeddinggemma`), via LangChain's
Ollama adapters.

**Frontend:** React 19 + Vite + Tailwind CSS 4, a single chat-centric page
rather than a traditional multi-page dashboard.

## Project structure

```
backend/app/
  api/                 FastAPI routers (students, resumes, job roles, analyzer,
                        ingestion, health, reports, consultation, chat sessions)
  scoring/              resume rubric grading, SKKNI skill-gap matching,
                        grounded narrative generation, consultation chat
  reporting/            PDF report (reportlab) + PNG poster (Pillow) generation
  ingestion/            SKKNI/curriculum PDF parsing, chunking, indexing
  retrieval/            semantic + lexical (BM25) search over ingested chunks
  resume/               PDF/DOCX/image resume parsing
  llm/                  chat + embeddings adapters over Ollama
  models.py, schemas.py, database.py, config.py

frontend/src/
  pages/Consultation.tsx        the main chat + context-panel page
  pages/IngestionAdmin.tsx      ingestion status/admin page
  components/                   ChatPanel, ContextPanel, upload/role/activity modals
  api/                           typed API clients per resource
  *Context.tsx                   student + chat-session state

data/
  raw/            source PDFs (SKKNI competency standard, university curriculum book)
  seed/            fixture students, activities, enrollments, job role definitions,
                    curated SKKNI-to-curriculum course mapping
  branding/        university logo used in report/poster output
  eval/            skill-gap evaluation harness (structural checks; accuracy labels
                    are filled in by a program advisor, not fabricated)
```

## Prerequisites

- PostgreSQL running locally, with the [`pgvector`](https://github.com/pgvector/pgvector)
  extension available.
- [Ollama](https://ollama.com) running locally with `qwen3.5:9b` and
  `embeddinggemma` pulled (`ollama pull qwen3.5:9b && ollama pull embeddinggemma`).
- Python 3.10+, Node.js 20+.

## Setup

### 1. Database

```bash
createdb career_skill_analyzer
psql career_skill_analyzer -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

All commands must be run from `backend/` — `app.main` only resolves relative
to that directory. Tables are created automatically on startup
(`Base.metadata.create_all`, no migration tool).

By default the app connects to `postgresql+asyncpg://<your-user>@localhost:5432/career_skill_analyzer`
and to Ollama at `http://localhost:11434`. Override any of these with
`CSA_`-prefixed environment variables (see `app/config.py` for the full list,
e.g. `CSA_DATABASE_URL`, `CSA_OLLAMA_HOST`).

Then ingest the source PDFs and load fixture data (both are idempotent, safe
to re-run):

```bash
python3 -c "
import asyncio
from app.database import SessionLocal
from app.ingestion.index_pipeline import run_full_ingestion
from app.seed.seed_data import run_seed

async def main():
    async with SessionLocal() as session:
        print(await run_full_ingestion(session))
        print(await run_seed(session))

asyncio.run(main())
"
```

(or use the "Synchronize now" button on the Ingestion admin page once the
frontend is running — the fixture-data seed step still needs the snippet
above the first time, since seeding validates SKKNI unit codes against
whatever has already been ingested.)

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, pick a fixture student from the student
switcher, upload a resume and/or pick a target role, and start a
consultation.

## API overview

All routes are prefixed with `/api`.

| Area | Endpoints |
| --- | --- |
| Students | `GET /students`, `GET /students/{id}/profile`, `POST`/`DELETE /students/{id}/projects[/{id}]` |
| Resumes | `POST /students/{id}/resume/upload`, `GET .../resume/latest`, `DELETE .../resume/{id}`, `GET /resumes/{id}/score` |
| Job roles | `GET /job-roles`, `GET /job-roles/resolve` |
| Skill-gap analysis | `POST /analyzer/skill-gap`, `GET /analyzer/skill-gap/{id}`, `GET /students/{id}/skill-gap/history` |
| Consultation chat | `POST /students/{id}/consult` |
| Chat sessions | `GET`/`POST /students/{id}/chat-sessions`, `GET`/`PATCH`/`DELETE .../chat-sessions/{id}`, `PATCH .../chat-sessions/{id}/pin` |
| Reports | `GET /students/{id}/consultation-report.pdf`, `.../consultation-poster.png`, `.../consultation-summary` |
| Ingestion | `POST /run`, `GET /runs`, `GET /status` |
| Health | `GET /health` |

Interactive docs are available at `http://localhost:8000/docs` once the
backend is running.

## Running tests

```bash
cd backend && source .venv/bin/activate
python -m pytest tests/unit                     # pure functions, no services needed
python -m pytest tests/integration tests/e2e    # needs Postgres + Ollama running, with data ingested/seeded
```

Use `python -m pytest`, not the bare `pytest` script — the bare script's
default import mode doesn't put `backend/` on `sys.path`, so `import app...`
fails with `ModuleNotFoundError: No module named 'app'`.

## Known limitations / next steps

- **No authentication.** The student switcher is a development convenience,
  not an access boundary.
- **No migration tool.** Schema changes require dropping and letting
  `create_all` recreate the affected table(s); there's no Alembic history.
- **Academic data is fixture data**, not connected to a real student
  information system — GPA, courses, and enrollments come from
  `data/seed/*.yaml`, not a live integration.
- **Report/poster generation is slow (3–5 minutes)** — it chains several
  sequential Ollama calls. Results are cached by an input fingerprint so
  repeat downloads for the same student/role/resume/activities are instant.
- **Skill-gap evaluation harness has no filled-in labels yet.**
  `data/eval/skill_gap_eval_set.yaml` spans 9 (student, role) pairs for a
  real accuracy measurement; it currently only runs structural checks until
  a program advisor reviews and labels expected outcomes.
- **Image-upload resumes (JPG/PNG) aren't wired in yet** — only PDF/DOCX are
  accepted today.
