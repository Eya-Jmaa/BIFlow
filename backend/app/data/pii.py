from __future__ import annotations

import re
from typing import Any

import phonenumbers
import polars as pl

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_LOOSE_RE = re.compile(r"^\+?[\d\s().-]{8,20}$")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
NAME_HINTS = ("name", "first_name", "last_name", "full_name", "customer_name")
ADDRESS_HINTS = ("address", "street", "zip", "cep", "postcode", "city")


def detect_pii(frame: pl.DataFrame, table_name: str, sample_size: int = 200) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    sample = frame.head(sample_size)
    for col in sample.columns:
        series = sample[col].drop_nulls().cast(pl.Utf8, strict=False)
        values = [v for v in series.head(50).to_list() if v]
        if not values:
            continue
        lowered = col.lower()
        kind = None
        confidence = 0.0
        if "email" in lowered or _majority(values, lambda v: bool(EMAIL_RE.match(v))):
            kind, confidence = "email", 0.95
        elif "phone" in lowered or "mobile" in lowered or _majority(values, _looks_like_phone):
            kind, confidence = "phone", 0.85
        elif any(h in lowered for h in NAME_HINTS):
            kind, confidence = "name", 0.7
        elif any(h in lowered for h in ADDRESS_HINTS):
            kind, confidence = "address", 0.7
        elif "cpf" in lowered or "ssn" in lowered or "passport" in lowered:
            kind, confidence = "national_id", 0.9
        elif _majority(values, lambda v: bool(UUID_RE.match(v))):
            kind, confidence = "identifier", 0.6
        if kind:
            flags.append(
                {
                    "table": table_name,
                    "column": col,
                    "pii_type": kind,
                    "confidence": confidence,
                    "action": "Do not send raw values to the LLM; statistics and masked samples only.",
                }
            )
    return flags


def mask_value(value: str, pii_type: str) -> str:
    if value is None:
        return ""
    if pii_type == "email" and "@" in value:
        name, domain = value.split("@", 1)
        return f"{name[:1]}***@{domain}"
    if pii_type == "phone":
        digits = re.sub(r"\D", "", value)
        return f"***{digits[-4:]}" if len(digits) >= 4 else "***"
    if len(value) <= 2:
        return "***"
    return f"{value[:1]}***{value[-1:]}"


def _majority(values: list[str], predicate) -> bool:
    if not values:
        return False
    hits = sum(1 for v in values if predicate(v))
    return hits / len(values) >= 0.5


def _looks_like_phone(value: str) -> bool:
    if not PHONE_LOOSE_RE.match(value or ""):
        return False
    try:
        parsed = phonenumbers.parse(value, None)
        return phonenumbers.is_possible_number(parsed)
    except Exception:
        return len(re.sub(r"\D", "", value)) >= 8
