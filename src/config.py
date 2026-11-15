"""Paths, thresholds and the Gemini settings read from .env for the VibeMatch agent."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SONGS_CSV = PROJECT_ROOT / "data" / "songs.csv"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "agent.log"

# --- Input guardrail ---
MAX_REQUEST_CHARS = 300
MIN_RELEVANCE = 1.0          # best KB BM25 score a request with no music words must reach

# --- Retrieval ---
DEFAULT_DOCS_K = 3           # knowledge docs retrieved per request
SONG_HITS_K = 5              # song docs retrieved per request

# --- Recommendations ---
DEFAULT_K = 5
MIN_K = 1
MAX_K = 20

# --- Self-check ---
MAX_ATTEMPTS = 3             # original plan + 2 revisions
MIN_SCORE_RATIO = 0.55       # top_score / max_score below this is "low confidence"
RANGE_TOLERANCE = 0.15       # top-3 mean may sit this far outside a doc range before it counts

# --- Explanation guardrail ---
MAX_EXPLANATION_CHARS = 1000

# --- LLM ---
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_GEMINI_FALLBACK_MODEL = "gemini-3.8-flash"   # set GEMINI_FALLBACK_MODEL=none to disable
DEFAULT_GEMINI_TIMEOUT = 30.0     # seconds per attempt; override with GEMINI_TIMEOUT
LLM_RETRY_DELAYS = (2.0, 5.0)     # backoff before retry 1 and retry 2 (timeouts / 5xx only)
LLM_TEMPERATURE = 0.2


def load_env() -> None:
    """Load .env from the project root if python-dotenv is installed; missing file or package is fine."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env")


def gemini_api_key() -> str:
    """Return the Gemini API key from the environment, or "" when unset or still the placeholder."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key or key.startswith("your-"):
        return ""
    return key


def gemini_model() -> str:
    """Return the Gemini model name from the environment, falling back to the default."""
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL


def gemini_fallback_model() -> str:
    """Return the model tried once after the main model fails; blank/unset uses the default, "none" disables it."""
    value = os.getenv("GEMINI_FALLBACK_MODEL", "").strip()
    if value.lower() == "none":
        return ""
    return value or DEFAULT_GEMINI_FALLBACK_MODEL


def gemini_timeout() -> float:
    """Return the per-attempt timeout in seconds from GEMINI_TIMEOUT; blank, invalid or <= 0 uses the default."""
    raw = os.getenv("GEMINI_TIMEOUT", "").strip()
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_GEMINI_TIMEOUT
    return value if value > 0 else DEFAULT_GEMINI_TIMEOUT
