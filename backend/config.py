import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Database
DATABASE_PATH = BASE_DIR / "deepshield.db"

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", "deepshield-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
REPORT_SIGNING_SECRET = os.getenv("REPORT_SIGNING_SECRET", JWT_SECRET)
SHARE_LINK_TTL_HOURS = int(os.getenv("SHARE_LINK_TTL_HOURS", "72"))

# External APIs (Fake News Detection)
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "") or LLM_API_KEY
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")
WORLDNEWS_API_KEY = os.getenv("WORLDNEWS_API_KEY", "")
NEWSMESH_API_KEY = os.getenv("NEWSMESH_API_KEY", "")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "")
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")
URLSCAN_API_KEY = os.getenv("URLSCAN_API_KEY", "")
URLSCAN_VISIBILITY = os.getenv("URLSCAN_VISIBILITY", "unlisted")
LINK_PROVIDER_POLL_ATTEMPTS = int(os.getenv("LINK_PROVIDER_POLL_ATTEMPTS", "4"))
LINK_PROVIDER_POLL_INTERVAL_SECONDS = float(os.getenv("LINK_PROVIDER_POLL_INTERVAL_SECONDS", "1.5"))
LINK_PROVIDER_TIMEOUT_SECONDS = float(os.getenv("LINK_PROVIDER_TIMEOUT_SECONDS", "12"))

# Uploads
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
EVIDENCE_DIR = BASE_DIR / "evidence"
EVIDENCE_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE_MB = 100

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
ALL_ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS | ALLOWED_AUDIO_EXTENSIONS
