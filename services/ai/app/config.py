import os

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi4-mini")
PORT = int(os.environ.get("PORT", "8100"))
RULES_PATH = os.environ.get("RULES_PATH")
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "20"))
OLLAMA_HEALTH_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_HEALTH_TIMEOUT_SECONDS", "2"))
