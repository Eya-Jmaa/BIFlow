#!/usr/bin/env python
"""Download the demo dataset.

BIFlow is demonstrated on UCI Online Retail — see
`data/documentation/uci-online-retail.md`. Nothing here fabricates rows: it
fetches the real public file and leaves it unmodified in `data/raw/`.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
URL = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"


def download_uci_online_retail() -> Path:
    """Fetch UCI Online Retail (541,909 rows, CC BY 4.0)."""
    destination = RAW / "uci_online_retail"
    destination.mkdir(parents=True, exist_ok=True)

    existing = list(destination.glob("*.xlsx")) + list(destination.glob("*.csv"))
    if existing:
        print(f"Already present: {existing[0]}")
        return destination

    print(f"Downloading {URL}")
    with httpx.Client(timeout=180.0, follow_redirects=True) as client:
        response = client.get(URL)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            archive.extractall(destination)

    for path in sorted(destination.iterdir()):
        print(f"  extracted {path.name} ({path.stat().st_size:,} bytes)")
    return destination


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    try:
        destination = download_uci_online_retail()
    except Exception as exc:  # noqa: BLE001 - the archive is occasionally offline
        print(f"Download failed: {exc}", file=sys.stderr)
        print(
            "\nThe UCI archive is sometimes unavailable. Download it by hand from\n"
            "  https://archive.ics.uci.edu/dataset/352/online+retail\n"
            f"and place the file in {RAW / 'uci_online_retail'}.\n"
            "Any CSV, Parquet or Excel file works — BIFlow is not tied to this one.",
            file=sys.stderr,
        )
        return 1

    print(
        f"\nReady. Upload the file from {destination} through the Datasets screen,\n"
        "then run the pipeline.\n\n"
        "Other sources listed in the brief (Olist, AdventureWorks, Telco Churn,\n"
        "NYC Taxi) also work without code changes, but are not used by this project."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
