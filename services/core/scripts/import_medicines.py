"""Import licensed medicine reference data into Core's Postgres.

    cd services/core
    # verified public dataset (downloads ~32 MB once, verifies sha256):
    python scripts/import_medicines.py --download --data-dir ./data/medicine-sources
    # or an already-downloaded copy (checksum still verified):
    python scripts/import_medicines.py --csv /path/to/indian_medicine_data.csv

Uses DATABASE_URL (same as the service). Re-running with the same file is a
no-op. The CSV is never committed to the repository.
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_session_factory  # noqa: E402
from app.medicine_import import (  # noqa: E402
    INDIAN_MEDICINE_DATASET,
    ImportAborted,
    ImportSpec,
    import_medicine_csv,
    sha256_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", type=Path, help="Path to an already-downloaded indian_medicine_data.csv")
    src.add_argument("--download", action="store_true", help="Download the verified public CSV first")
    parser.add_argument("--data-dir", type=Path, default=Path("data/medicine-sources"))
    args = parser.parse_args()

    meta = INDIAN_MEDICINE_DATASET
    if args.download:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        path = args.data_dir / "indian_medicine_data.csv"
        if not path.exists() or sha256_file(path) != meta["sha256"]:
            print(f"downloading {meta['source_url']} ...")
            urllib.request.urlretrieve(meta["source_url"], path)  # noqa: S310 - fixed https URL
    else:
        path = args.csv

    spec = ImportSpec(**meta)
    session = get_session_factory()()
    try:
        report = import_medicine_csv(session, path, spec)
    except ImportAborted as exc:
        session.rollback()
        print(f"ABORTED, nothing imported: {exc}", file=sys.stderr)
        return 2
    finally:
        session.close()

    print(f"source      {meta['name']} ({meta['license']})")
    print(f"sha256      {report.sha256} (verified)")
    print(f"rows read   {report.rows_read}")
    print(f"inserted    {report.inserted}")
    print(f"updated     {report.updated}")
    print(f"unchanged   {report.unchanged}")
    print(f"rejected    {report.rejected}")
    print(f"matchable   {report.matchable}")
    for line_no, reason in report.reject_samples[:10]:
        print(f"  rejected line {line_no}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
