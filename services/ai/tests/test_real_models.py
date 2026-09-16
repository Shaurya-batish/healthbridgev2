"""OPT-IN real-model integration checks. Nothing here is mocked.

Runs the real faster-whisper model on real, non-sensitive speech and (if
installed) real Argos Translate packages on real text. Skipped unless
explicitly enabled, because it needs model downloads and minutes of CPU:

    HB_REAL_MODELS=1 HB_SPEECH_DIR=/path/to/clips pytest tests/test_real_models.py -s

HB_SPEECH_DIR must contain `<fleurs_lang>_<n>.wav` with a matching `.txt`
reference transcript, e.g. hi_in_0.wav / hi_in_0.txt. The clips used for the
recorded evidence are Google FLEURS dev-split utterances (CC-BY 4.0), fetched
by streaming the dataset archive; they are not committed.

Pass criteria are deliberately modest and objective: the original-language
transcript must be in the right script and close to the reference (character
error rate), and the English translation must be non-empty Latin-script text.
Whether a translation is *meaningful* is judged by a human reading the printed
output -- that judgement is recorded in docs, not claimed by this test.
"""
from __future__ import annotations

import base64
import os
import re
import unicodedata
from pathlib import Path

import pytest

from app import transcribe, translate

ENABLED = os.environ.get("HB_REAL_MODELS") == "1"
SPEECH_DIR = Path(os.environ.get("HB_SPEECH_DIR", "__missing__"))

pytestmark = pytest.mark.skipif(not ENABLED, reason="set HB_REAL_MODELS=1 to run real Whisper/Argos checks")

FLEURS_TO_APP = {"hi_in": "hi", "ta_in": "ta", "bn_in": "bn", "mr_in": "mr", "pa_in": "pa"}
SCRIPT_RANGES = {
    "hi": (0x0900, 0x097F),  # Devanagari
    "mr": (0x0900, 0x097F),
    "bn": (0x0980, 0x09FF),
    "pa": (0x0A00, 0x0A7F),  # Gurmukhi
    "ta": (0x0B80, 0x0BFF),
}
MAX_CER = {"hi": 0.35, "ta": 0.45}  # Whisper "small" is weaker on Tamil


def _clips():
    if not SPEECH_DIR.is_dir():
        return []
    # Only canonical FLEURS clip names (e.g. hi_in_0.wav) with a reference transcript.
    return sorted(p for p in SPEECH_DIR.glob("*.wav") if re.fullmatch(r"[a-z]{2}_in_\d+", p.stem) and p.with_suffix(".txt").exists())


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text.lower())
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", "", text)


def _cer(reference: str, hypothesis: str) -> float:
    ref, hyp = _normalise(reference), _normalise(hypothesis)
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i]
        for j, hc in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / max(1, len(ref))


def _script_share(text: str, lang: str) -> float:
    lo, hi = SCRIPT_RANGES[lang]
    letters = [c for c in text if c.isalpha()]
    return sum(lo <= ord(c) <= hi for c in letters) / max(1, len(letters))


@pytest.mark.parametrize("clip", _clips(), ids=lambda p: p.stem)
def test_real_whisper_transcribes_original_language_and_translates_to_english(clip, monkeypatch):
    monkeypatch.setenv("AI_MODE", "local")
    lang = FLEURS_TO_APP[clip.stem.rsplit("_", 1)[0]]
    reference = clip.with_suffix(".txt").read_text(encoding="utf-8")
    audio_b64 = base64.b64encode(clip.read_bytes()).decode()

    result = transcribe.transcribe_and_translate(audio_b64, language=lang, mime_type="audio/wav")
    cer = _cer(reference, result.transcript)
    print(f"\n[{clip.stem}] lang={lang} model={result.model} duration={result.duration_seconds}s")
    print(f"  reference : {reference}")
    print(f"  transcript: {result.transcript}")
    print(f"  english   : {result.translation_en}")
    print(f"  warnings  : transcript={list(result.transcript_warnings)} translation={list(result.translation_warnings)}")
    print(f"  CER       : {cer:.3f}")

    assert _script_share(result.transcript, lang) > 0.8, "transcript is not in the expected script"
    assert cer <= MAX_CER.get(lang, 0.5), f"character error rate {cer:.2f} too high"
    latin = [c for c in result.translation_en if c.isalpha()]
    assert len(result.translation_en.split()) >= 3
    assert latin and sum(c.isascii() for c in latin) / len(latin) > 0.95, "translation is not English text"


def _loaded_languages() -> list[str]:
    translate._warm()  # load the engine synchronously through the same path as the service
    return translate.available_languages()


@pytest.mark.parametrize("lang", ["hi", "bn"])
def test_real_argos_translates_typed_text_when_package_installed(lang, monkeypatch):
    monkeypatch.setenv("AI_MODE", "local")
    if lang not in _loaded_languages():
        pytest.skip(f"no installed {lang}->en Argos package on this host")
    sample = {"hi": "बच्चे को तीन दिन से तेज़ बुखार है और वह दूध नहीं पी रहा है।", "bn": "শিশুটির তিন দিন ধরে জ্বর এবং সে দুধ খাচ্ছে না।"}[lang]
    english = translate.translate_to_english(sample, lang)
    print(f"\n[argos {lang}] {sample}\n  -> {english}")
    latin = [c for c in english if c.isalpha()]
    assert len(english.split()) >= 4
    assert sum(c.isascii() for c in latin) / len(latin) > 0.95


@pytest.mark.parametrize("lang", ["pa", "mr", "ta"])
def test_languages_without_argos_packages_report_unavailable_honestly(lang, monkeypatch):
    monkeypatch.setenv("AI_MODE", "local")
    if lang in _loaded_languages():
        pytest.skip(f"{lang}->en unexpectedly installed; not an unavailable language here")
    with pytest.raises(translate.TranslationUnavailable):
        translate.translate_to_english("ਬੁਖਾਰ", lang)
