"""Local configuration shared by startup and clients. Never prints credentials."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
CONFIG = LOCAL / "settings.json"


def load_config():
    if not CONFIG.exists():
        raise RuntimeError("Local configuration missing. Run scripts/local.ps1 init first.")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def configure_environment():
    config = load_config()
    # Override inherited/cloud settings. Do not load the existing deployment .env.
    os.environ.update({
        "DATABASE_URL": config["database_url"],
        "PERSONAL_MODE": "true",
        "PERSONAL_API_KEY": config["personal_api_key"],
        "RELAY_SECRET": config["relay_secret"],
        "MNEME_OFFLINE": "true",
        "LOCAL_EMBEDDINGS_FALLBACK": "false",
        "HELIOS_ENABLED": "true",
    })
    for key in ("OPENAI_API_KEY", "RESEND_API_KEY", "EMAIL_FROM"):
        os.environ.pop(key, None)
    return config
