#!/usr/bin/env python
"""Download public demo datasets into data/raw without fabricating business rows."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"


def download_uci_online_retail() -> Path:
    """UCI Online Retail — real public transactional dataset."""
    url = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"
    dest = RAW / "uci_online_retail"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            zf.extractall(dest)
    print(f"Extracted to {dest}")
    return dest


def print_olist_instructions() -> None:
    print(
        """
Olist Brazilian E-Commerce is the primary recommended demo dataset.

It is published by Olist on Kaggle:
https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

License/usage: follow the Kaggle dataset terms. Do not modify the original files.

After download, place the CSV files in:
  data/raw/olist/

Expected files include:
  olist_orders_dataset.csv
  olist_order_items_dataset.csv
  olist_order_payments_dataset.csv
  olist_customers_dataset.csv
  olist_products_dataset.csv
  olist_order_reviews_dataset.csv
  olist_geolocation_dataset.csv
  olist_sellers_dataset.csv
  product_category_name_translation.csv

If you have the Kaggle CLI configured:
  kaggle datasets download -d olistbr/brazilian-ecommerce -p data/raw/olist --unzip
"""
    )


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    print_olist_instructions()
    try:
        download_uci_online_retail()
    except Exception as exc:
        print(f"UCI download skipped: {exc}")
        print("You can still upload CSVs through the BIFlow UI.")
