import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analyzer, chat_sessions, consultation, health, ingestion, job_roles, reports, resumes, students
from app.database import init_models

# No handler exists anywhere in this app otherwise -- without this, every
# logger.info() in app.llm.chat/app.llm.embeddings (Ollama call timing,
# in-flight-call counts) is silently dropped rather than reaching the
# console, since the root logger has no handler by default and Python's
# logging "last resort" fallback only surfaces WARNING and above.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx/httpcore log every single HTTP request at INFO -- with basicConfig
# now giving them a handler too, that would otherwise drown out the app's own
# Ollama-timing diagnostics on every request.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    yield


app = FastAPI(title="PresConsult AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(students.router, prefix="/api")
app.include_router(resumes.router, prefix="/api")
app.include_router(job_roles.router, prefix="/api")
app.include_router(analyzer.router, prefix="/api")
app.include_router(ingestion.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(consultation.router, prefix="/api")
app.include_router(chat_sessions.router, prefix="/api")
