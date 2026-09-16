"""Installs the real Argos Translate <lang>->English packages the ASHA app can use
for TYPED complaints. Run once per host (needs internet once; translation is
offline afterwards):

    python scripts/install_translation_packages.py

Only languages for which Argos actually publishes a package are installed.
At the time of writing that is Hindi (hi) and Bengali (bn). Punjabi (pa),
Marathi (mr) and Tamil (ta) have no published package; the script reports
them as unavailable rather than pretending. Voice capture in those languages
still works through Whisper's own speech translation.
"""
from __future__ import annotations

import sys

WANTED = ("hi", "pa", "bn", "mr", "ta")


def main() -> int:
    try:
        from argostranslate import package
    except ImportError:
        print("argostranslate is not installed: pip install argostranslate", file=sys.stderr)
        return 1

    package.update_package_index()
    available = {(p.from_code, p.to_code): p for p in package.get_available_packages()}
    installed = {(p.from_code, p.to_code) for p in package.get_installed_packages()}

    status = 0
    for code in WANTED:
        pair = (code, "en")
        if pair in installed:
            print(f"{code}->en: already installed")
            continue
        pkg = available.get(pair)
        if pkg is None:
            print(f"{code}->en: NOT AVAILABLE from the Argos package index (typed translation unsupported)")
            continue
        print(f"{code}->en: downloading {pkg} ...")
        try:
            package.install_from_path(pkg.download())
            print(f"{code}->en: installed")
        except Exception as exc:  # network or disk failure
            print(f"{code}->en: FAILED: {exc}", file=sys.stderr)
            status = 2
    return status


if __name__ == "__main__":
    raise SystemExit(main())
