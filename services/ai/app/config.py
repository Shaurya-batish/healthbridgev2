import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi4-mini")
PORT = int(os.environ.get("PORT", "8100"))
RULES_PATH = os.environ.get("RULES_PATH")
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "20"))
OLLAMA_HEALTH_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_HEALTH_TIMEOUT_SECONDS", "2"))
# "small" handles Hindi/Bengali/Tamil etc. usably on CPU int8; larger models
# are more accurate but several times slower on PHC-grade hardware.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")

# When the AI service is exposed publicly (Cloudflare quick tunnel), every
# request except /health must carry this value in X-AI-Key. Unset = no check
# (compose-internal / localhost use only).
AI_SHARED_SECRET = os.environ.get("AI_SHARED_SECRET") or None

# "local"    -- Whisper + Ollama run on this machine (dev/demo laptop, PHC box).
# "degraded" -- hosted build with no model runtime. Whisper and Ollama are
#               never loaded or probed; /health says so truthfully and every
#               AI endpoint returns 503 immediately so the client drops to the
#               structured checklist (same rule engine) without waiting on a
#               timeout. See docs/DEPLOYMENT.md.
_VALID_AI_MODES = ("local", "degraded")


def ai_mode() -> str:
    """Read at call time (not import time) so tests can flip it with monkeypatch."""
    mode = os.environ.get("AI_MODE", "local").strip().lower()
    if mode not in _VALID_AI_MODES:
        raise RuntimeError(f"AI_MODE must be one of {_VALID_AI_MODES}, got {mode!r}")
    return mode


def is_degraded() -> bool:
    return ai_mode() == "degraded"
