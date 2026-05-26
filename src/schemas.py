"""Pydantic schemas for every agent output + the orchestrator's aggregated view.

Each agent has its own rich output type (specific to its domain) but they all
extend the same AgentReport base so the orchestrator can treat them uniformly
without losing type information.
"""
from typing import Literal
from pydantic import BaseModel, Field

Severity = Literal["HIGH", "MEDIUM", "LOW", "INFO"]


# ===== Base =====
class AgentReport(BaseModel):
    """Common envelope every agent returns. extra='forbid' catches drift."""
    model_config = {"extra": "forbid"}

    agent_name: str
    status: Literal["success", "error"] = "success"
    summary: str
    error: str | None = None


# ===== Agent 1: Price Anomaly =====
class PriceAnomaly(BaseModel):
    model_config = {"extra": "forbid"}
    offer_id: str
    offer_name: str
    product_id: str
    product_name: str
    offer_price: float
    product_base_price: float
    currency: str
    severity: Severity
    reason: str


class PriceAnomalyReport(AgentReport):
    agent_name: Literal["price_anomaly"] = "price_anomaly"
    anomalies: list[PriceAnomaly] = Field(default_factory=list)


# ===== Agent 2: Daily Deals Anomaly =====
class DealAnomaly(BaseModel):
    model_config = {"extra": "forbid"}
    product_id: str
    product_name: str
    original_price: float
    deal_price: float
    discount_pct: float
    currency: str
    risk_level: Severity
    assessment: str


class DealsAnomalyReport(AgentReport):
    agent_name: Literal["deals_anomaly"] = "deals_anomaly"
    anomalies: list[DealAnomaly] = Field(default_factory=list)


# ===== Agent 3: Sales Anomaly =====
class SalesAnomaly(BaseModel):
    model_config = {"extra": "forbid"}
    product_id: str
    product_name: str
    category: str
    sold_today: int
    sold_yesterday: int
    avg_7day: float
    pct_vs_avg: float
    severity: Severity
    likely_cause: str


class SalesAnomalyReport(AgentReport):
    agent_name: Literal["sales_anomaly"] = "sales_anomaly"
    anomalies: list[SalesAnomaly] = Field(default_factory=list)


# ===== Agent 4: Nordic Event Manager =====
class UpcomingEvent(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    event_date: str            # ISO YYYY-MM-DD
    days_until: int
    countries: list[str]
    affected_categories: list[str]
    severity: Severity
    recommendation: str


class EventManagerReport(AgentReport):
    agent_name: Literal["event_manager"] = "event_manager"
    upcoming: list[UpcomingEvent] = Field(default_factory=list)


# ===== Agent 5: Click Spike =====
class ClickSpike(BaseModel):
    model_config = {"extra": "forbid"}
    product_id: str
    product_name: str
    category: str
    clicks_today: int
    clicks_yesterday: int
    pct_change: float
    dominance_in_category: float     # how many times higher than #2 in same category
    severity: Severity
    interpretation: str


class ClickSpikeReport(AgentReport):
    agent_name: Literal["click_spike"] = "click_spike"
    spikes: list[ClickSpike] = Field(default_factory=list)


# ===== Aggregated orchestrator output =====
class OrchestratorResult(BaseModel):
    """What the orchestrator returns after fan-in. The HTML report is rendered separately."""
    model_config = {"extra": "forbid"}
    target_date: str
    price: PriceAnomalyReport
    deals: DealsAnomalyReport
    sales: SalesAnomalyReport
    events: EventManagerReport
    clicks: ClickSpikeReport
    total_runtime_sec: float
