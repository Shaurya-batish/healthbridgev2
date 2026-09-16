"""Local, offline machine translation of TYPED complaints into English.

Whisper translates speech, not typed text, so a typed Hindi complaint needs
its own real translation path before it can reach the English-only
extraction prompt. This adapter wraps Argos Translate (OpenNMT/CTranslate2
models, MIT licensed, runs fully offline once a language package is
installed) -- no cloud service, consistent with CLAUDE.md.

Honesty rules this module enforces:
- A language is only "supported" if its <lang>->en package is actually
  installed on this host. Argos publishes packages for Hindi and Bengali;
  none exist for Punjabi, Marathi or Tamil at the time of writing, so those
  report `translation_unavailable` and the ASHA must supply the English text
  herself (or use voice, which Whisper translates, or the checklist).
- Nothing here is ever asked to judge severity or rewrite clinical meaning;
  the output is labelled as machine translation and must be confirmed by
  the ASHA before extraction.

Runtime notes (verified 2026-09-15 with argostranslate 1.11.0):
- The Bengali 1.9 package's bundled Stanza sentence splitter crashes under
  stanza 1.10 (KeyError: 'packages'). Argos' own MiniSBD splitter works for
  both Hindi and Bengali, so it is the default here unless ARGOS_CHUNK_TYPE
  is set explicitly. This must be set before argostranslate is imported.
- Importing argostranslate pulls in torch and takes many seconds. /health
  must never block on that, so the import is warmed in a background thread
  and languages are reported only once the engine has loaded.

Like faster-whisper, the dependency is imported lazily so the service still
starts (and every other endpoint still works) when Argos isn't installed.
"""
from __future__ import annotations

import os
import threading

from . import config

ENGINE = "argostranslate"

os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")

_warm_lock = threading.Lock()
_warm_started = False
_engine_ready = False


class TranslationUnavailable(Exception):
    """Argos isn't installed, the language package is missing, or translation failed."""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(message or reason)
        self.reason = reason


def engine_loaded() -> bool:
    # A flag, not `name in sys.modules`: a module is registered there at the
    # START of its import, so checking it could send a health request into a
    # half-initialised package and block it on the import lock.
    return _engine_ready


def _warm() -> None:
    global _engine_ready
    try:
        import argostranslate.translate  # noqa: F401
    except Exception:
        return  # not installed or broken: stays unavailable, reported honestly
    _engine_ready = True


def start_warmup() -> None:
    """Begin importing Argos in the background (idempotent, non-blocking)."""
    global _warm_started
    with _warm_lock:
        if _warm_started or engine_loaded():
            return
        _warm_started = True
    threading.Thread(target=_warm, name="argos-warmup", daemon=True).start()


def _installed_pairs() -> dict[str, object]:
    """Maps source language code -> Argos translation object into English."""
    try:
        from argostranslate import translate as argos_translate
    except ImportError:
        return {}
    languages = {lang.code: lang for lang in argos_translate.get_installed_languages()}
    english = languages.get("en")
    if english is None:
        return {}
    pairs: dict[str, object] = {}
    for code, lang in languages.items():
        if code == "en":
            continue
        translation = lang.get_translation(english)
        if translation is not None:
            pairs[code] = translation
    return pairs


def available_languages() -> list[str]:
    """Source languages this host can really translate into English right now.

    Non-blocking: until the engine has finished loading this returns [] and
    starts the warm-up, so a health check never waits on a torch import.
    """
    if config.is_degraded():
        return []
    if not engine_loaded():
        start_warmup()
        return []
    return sorted(_installed_pairs())


def engine_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("argostranslate")
    except Exception:
        return None


def translate_to_english(text: str, source_language: str) -> str:
    if config.is_degraded():
        raise TranslationUnavailable("degraded_mode", "AI_MODE=degraded: translation is disabled on this deployment")
    if source_language == "en":
        return text
    try:
        import argostranslate  # noqa: F401
    except ImportError as exc:
        raise TranslationUnavailable("engine_not_installed", "argostranslate is not installed") from exc
    translation = _installed_pairs().get(source_language)
    if translation is None:
        raise TranslationUnavailable("language_not_installed", f"No {source_language}->en package is installed")
    try:
        english = translation.translate(text)  # type: ignore[attr-defined]
    except Exception as exc:
        raise TranslationUnavailable("translation_failed", f"Translation failed: {exc}") from exc
    return (english or "").strip()
