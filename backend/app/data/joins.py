from __future__ import annotations

from typing import Any

import polars as pl
from pydantic import BaseModel, Field


class JoinCandidate(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    overlap_ratio: float
    source_uniqueness: float
    target_uniqueness: float
    cardinality: str
    confidence: float
    validated: bool
    method: str
    evidence: dict[str, Any] = Field(default_factory=dict)


def discover_joins(tables: dict[str, pl.DataFrame], min_overlap: float = 0.6) -> list[JoinCandidate]:
    """Statistically validate candidate relationships. Name similarity is never sufficient."""
    candidates: list[JoinCandidate] = []
    names = list(tables.keys())
    for i, left_name in enumerate(names):
        left = tables[left_name]
        for right_name in names[i + 1 :]:
            right = tables[right_name]
            for left_col in left.columns:
                for right_col in right.columns:
                    score = _name_affinity(left_col, right_col, left_name, right_name)
                    if score < 0.35 and left_col.lower() != right_col.lower():
                        continue
                    if not _compatible_types(left[left_col].dtype, right[right_col].dtype):
                        continue
                    candidate = _validate_pair(left_name, left, left_col, right_name, right, right_col)
                    if candidate and candidate.overlap_ratio >= min_overlap:
                        candidates.append(candidate)
    candidates.sort(key=lambda item: item.confidence, reverse=True)
    return candidates


def _validate_pair(
    left_name: str,
    left: pl.DataFrame,
    left_col: str,
    right_name: str,
    right: pl.DataFrame,
    right_col: str,
) -> JoinCandidate | None:
    left_vals = left[left_col].drop_nulls()
    right_vals = right[right_col].drop_nulls()
    if left_vals.len() == 0 or right_vals.len() == 0:
        return None
    left_unique = left_vals.n_unique()
    right_unique = right_vals.n_unique()
    # Sample-friendly overlap using unique sets; cap for memory.
    left_set = set(left_vals.unique().head(50_000).to_list())
    right_set = set(right_vals.unique().head(50_000).to_list())
    if not left_set or not right_set:
        return None
    intersection = left_set & right_set
    overlap = len(intersection) / min(len(left_set), len(right_set))
    if overlap < 0.2:
        return None
    left_uniqueness = left_unique / max(left.height, 1)
    right_uniqueness = right_unique / max(right.height, 1)
    cardinality = _cardinality(left_uniqueness, right_uniqueness)
    name_boost = 0.15 if left_col.lower() == right_col.lower() else 0.0
    confidence = min(1.0, overlap * 0.75 + min(left_uniqueness, right_uniqueness) * 0.1 + name_boost)
    validated = overlap >= 0.6 and len(intersection) >= 1
    return JoinCandidate(
        source_table=left_name,
        source_column=left_col,
        target_table=right_name,
        target_column=right_col,
        overlap_ratio=round(overlap, 4),
        source_uniqueness=round(left_uniqueness, 4),
        target_uniqueness=round(right_uniqueness, 4),
        cardinality=cardinality,
        confidence=round(confidence, 4),
        validated=validated,
        method="value_overlap+uniqueness+name_affinity",
        evidence={
            "intersection_size": len(intersection),
            "left_unique_sampled": len(left_set),
            "right_unique_sampled": len(right_set),
        },
    )


def _cardinality(left_u: float, right_u: float) -> str:
    if left_u >= 0.95 and right_u >= 0.95:
        return "one_to_one"
    if left_u >= 0.95:
        return "one_to_many"
    if right_u >= 0.95:
        return "many_to_one"
    return "many_to_many"


def _name_affinity(left_col: str, right_col: str, left_table: str, right_table: str) -> float:
    l = left_col.lower()
    r = right_col.lower()
    if l == r:
        return 1.0
    if l.endswith("_id") and r.endswith("_id"):
        l_ent = l[:-3]
        r_ent = r[:-3]
        if l_ent in right_table.lower() or r_ent in left_table.lower():
            return 0.85
        return 0.45
    if l in r or r in l:
        return 0.6
    return 0.1


def _compatible_types(left, right) -> bool:
    left_s, right_s = str(left).lower(), str(right).lower()
    if left_s == right_s:
        return True
    numeric = ("int", "uint", "float", "decimal")
    if any(x in left_s for x in numeric) and any(x in right_s for x in numeric):
        return True
    stringy = ("utf8", "string", "categorical")
    return any(x in left_s for x in stringy) and any(x in right_s for x in stringy)
