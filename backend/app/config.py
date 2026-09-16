from pathlib import Path

from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
SEED_DATA_DIR = DATA_DIR / "seed"
EVAL_DATA_DIR = DATA_DIR / "eval"
UPLOADS_DIR = DATA_DIR / "uploads"
BRANDING_DIR = DATA_DIR / "branding"
UNIVERSITY_LOGO_PATH = BRANDING_DIR / "university_logo.png"


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://mac@localhost:5432/career_skill_analyzer"
    ollama_host: str = "http://localhost:11434"
    embedding_model: str = "embeddinggemma"
    embedding_dim: int = 768
    chat_model: str = "qwen3.5:9b"

    # Source documents (see app/ingestion/index_pipeline.py)
    skkni_pdf_filename: str = "SKKNI_2026-103.pdf"
    curriculum_pdf_filename: str = "IS_Curriculum_Book_2025.pdf"

    model_config = {"env_prefix": "CSA_"}

    @property
    def skkni_pdf_path(self) -> Path:
        return RAW_DATA_DIR / self.skkni_pdf_filename

    @property
    def curriculum_pdf_path(self) -> Path:
        return RAW_DATA_DIR / self.curriculum_pdf_filename


settings = Settings()
