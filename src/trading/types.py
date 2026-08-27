"""Shared immutable trading contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class OrderIntent:
    client_order_id: str
    ticker: str
    side: str
    order_type: str
    quantity: float
    notional: float
    reference_price: float
    limit_price: Optional[float]
    trading_session: str
    time_in_force: str
    target_weight: float
    analysis_position_cap_pct: float
    analysis_score: float
    learned_score: Optional[float]
    combined_score: float
    analysis_id: str
    data_source: str
    uses_fallback_data: bool
    data_is_authoritative: bool = False
    tokenize: bool = False
    rationale: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: List[str]
    order: OrderIntent
    calculated_notional: float
    projected_position_pct: float


@dataclass(frozen=True)
class ExecutionReport:
    client_order_id: str
    ticker: str
    side: str
    status: str
    filled_quantity: float
    average_price: float
    fee: float
    broker_order_id: Optional[str] = None
    message: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class PortfolioSnapshot:
    cash: float
    quantities: Dict[str, float] = field(default_factory=dict)
    prices: Dict[str, float] = field(default_factory=dict)
    start_of_day_equity: float = 0.0
    daily_traded_notional: float = 0.0
    trading_date: str = ""

    @property
    def equity(self) -> float:
        holdings_value = sum(
            quantity * float(self.prices.get(ticker, 0.0))
            for ticker, quantity in self.quantities.items()
        )
        return self.cash + holdings_value

    def position_value(self, ticker: str) -> float:
        return float(self.quantities.get(ticker, 0.0)) * float(self.prices.get(ticker, 0.0))

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)
