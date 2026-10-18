import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_FILE = PROJECT_ROOT / "data" / "hankevahti.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_FILE.as_posix()}")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8080"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip()
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()
AI_PROVIDER_LABEL = {"gemini": "Google Gemini", "openai": "OpenAI"}.get(AI_PROVIDER, "tuntematon AI-palvelu")
NOTIFICATION_EMAIL_TO = os.getenv("NOTIFICATION_EMAIL_TO", "").strip() or None
_notification_min_score = os.getenv("NOTIFICATION_MIN_RELEVANCE_SCORE", "").strip()
NOTIFICATION_MIN_RELEVANCE_SCORE = int(_notification_min_score) if _notification_min_score else None
NOTIFICATION_RUN_TIME = os.getenv("NOTIFICATION_RUN_TIME", "09:00").strip()
