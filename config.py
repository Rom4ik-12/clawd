import os
from dotenv import load_dotenv

load_dotenv()

# ─── Owner ────────────────────────────────────────────────────────────────────
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
OWNER_NAME = os.getenv("OWNER_NAME", "Владелец")
SAFE_MODE = os.getenv("SAFE_MODE", "False").lower() in ("true", "1", "yes")

# ─── LLM Providers ────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
CODEXSALE_API_KEY = os.getenv("CODEXSALE_API_KEY", "")
RUNIC_API_KEY = os.getenv("RUNIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ─── Custom OpenAI-compatible API ─────────────────────────────────────────────
# Любой OpenAI-совместимый эндпоинт: LMStudio, Ollama, Together, Groq и т.д.
# Пример: CUSTOM_API_BASE_URL=http://localhost:11434/v1
CUSTOM_API_KEY      = os.getenv("CUSTOM_API_KEY", "dummy")
CUSTOM_API_BASE_URL = os.getenv("CUSTOM_API_BASE_URL", "")  # пусто = не используется
CUSTOM_API_MODEL    = os.getenv("CUSTOM_API_MODEL", "")     # имя модели на том эндпоинте

# ─── Models ───────────────────────────────────────────────────────────────────
# Основные текстовые модели — пробуем по порядку (codexsale сначала, custom как запасной)
_custom_model_entry = ([f"custom/{CUSTOM_API_MODEL}"] if CUSTOM_API_BASE_URL and CUSTOM_API_MODEL else [])

LLM_MODELS = [
    "codexsale/gpt-5.5",
    "codexsale/gpt-5.4",
    "codexsale/gpt-5.4-mini",
    "codexsale/gpt-4o",
    "codexsale/claude-3-5-sonnet",
] + _custom_model_entry + [
    "runic/minimax-m3",
    "moonshotai/kimi-k2.6:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
]

# Модели с поддержкой зрения (vision)
_custom_vision_entry = (
    ["custom/gemini-3-flash", "custom/claude-sonnet-4-6", "custom/gemini-3.5-flash-low"]
    if CUSTOM_API_BASE_URL else []
)

VISION_MODELS = _custom_vision_entry + [
    "gemini/gemini-3.5-flash",   # Google Gemini — основной vision
    "runic/minimax-m3",
    "codexsale/gpt-4o",
]

# STT — транскрибация аудио
STT_MODEL = "openai/gpt-4o-transcribe"  # через codexsale_client

# ─── Telegram ─────────────────────────────────────────────────────────────────
API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SESSION_NAME = os.getenv("SESSION_NAME", "clawd")
PANEL_BOT_TOKEN = os.getenv("PANEL_BOT_TOKEN", "")
PANEL_BOT_USERNAME = os.getenv("PANEL_BOT_USERNAME", "")

# ─── SearXNG ──────────────────────────────────────────────────────────────────
SEARXNG_URL = os.getenv("SEARXNG_URL", "https://searx.be")

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "memory.db")
VECTOR_DB_PATH = os.path.join(BASE_DIR, "database", "vector_db")

# ─── Timezone ─────────────────────────────────────────────────────────────────
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")


def local_now():
    """Текущее время в настроенном часовом поясе."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from memory.sqlite import get_setting
    tz = get_setting("timezone", TIMEZONE)
    try:
        return datetime.now(ZoneInfo(tz))
    except Exception:
        return datetime.now(ZoneInfo(TIMEZONE))
