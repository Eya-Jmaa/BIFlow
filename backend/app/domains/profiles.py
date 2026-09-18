from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DomainProfile(BaseModel):
    domain: str
    business_terms: list[str] = Field(default_factory=list)
    common_dimensions: list[str] = Field(default_factory=list)
    common_metrics: list[str] = Field(default_factory=list)
    common_kpis: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)


DOMAIN_LIBRARY: dict[str, DomainProfile] = {
    "general": DomainProfile(
        domain="general",
        business_terms=["performance", "volume", "quality"],
        common_dimensions=["date", "category", "status"],
        common_metrics=["count", "total", "average"],
        common_kpis=["record_count", "completeness"],
        rules=["Prefer measures from numeric columns and dimensions from low-cardinality categoricals."],
    ),
    "ecommerce": DomainProfile(
        domain="ecommerce",
        business_terms=["order", "customer", "product", "payment", "delivery", "revenue"],
        common_dimensions=["order_date", "customer", "product", "category", "region", "payment_type"],
        common_metrics=["revenue", "orders", "customers", "quantity", "delivery_days"],
        common_kpis=["revenue", "order_count", "average_order_value", "unique_customers"],
        rules=["Monetary columns should not be negative when used as revenue.", "Join orders to payments/items before revenue KPIs."],
    ),
    "retail": DomainProfile(domain="retail", business_terms=["sku", "store", "basket"], common_kpis=["sales", "units"]),
    "telecommunications": DomainProfile(domain="telecommunications", business_terms=["churn", "arpu"], common_kpis=["arpu", "churn_rate"]),
    "banking": DomainProfile(domain="banking", business_terms=["balance", "transaction"], common_kpis=["transaction_volume"]),
    "finance": DomainProfile(domain="finance", business_terms=["pnl", "exposure"], common_kpis=["net_amount"]),
    "transport": DomainProfile(domain="transport", business_terms=["route", "delay"], common_kpis=["on_time_rate"]),
    "tourism": DomainProfile(domain="tourism", business_terms=["booking", "occupancy"], common_kpis=["occupancy"]),
    "health": DomainProfile(domain="health", business_terms=["encounter", "claim"], common_kpis=["encounter_count"]),
    "public_services": DomainProfile(domain="public_services", business_terms=["case", "citizen"], common_kpis=["case_volume"]),
    "energy": DomainProfile(domain="energy", business_terms=["consumption", "meter"], common_kpis=["consumption"]),
    "marketing": DomainProfile(domain="marketing", business_terms=["campaign", "conversion"], common_kpis=["conversion_rate"]),
}


def infer_domain(objective: str, columns: list[str]) -> str:
    blob = f"{objective} {' '.join(columns)}".lower()
    scores: dict[str, int] = {}
    for name, profile in DOMAIN_LIBRARY.items():
        score = 0
        for term in profile.business_terms + profile.common_metrics + profile.common_dimensions:
            if term.lower() in blob:
                score += 1
        scores[name] = score
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def get_domain(name: str) -> DomainProfile:
    return DOMAIN_LIBRARY.get(name, DOMAIN_LIBRARY["general"])
