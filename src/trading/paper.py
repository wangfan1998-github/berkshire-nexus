"""Persistent deterministic paper broker with an append-only execution journal."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Union
from uuid import uuid4

from .types import ExecutionReport, PortfolioSnapshot, RiskDecision


class PaperBroker:
    def __init__(
        self,
        state_directory: Union[Path, str],
        *,
        initial_cash: float = 100_000.0,
        commission_bps: float = 1.0,
        slippage_bps: float = 2.0,
    ):
        self.state_directory = Path(state_directory)
        self.state_path = self.state_directory / "paper_portfolio.json"
        self.journal_path = self.state_directory / "paper_executions.jsonl"
        self.initial_cash = float(initial_cash)
        self.commission_bps = float(commission_bps)
        self.slippage_bps = float(slippage_bps)

    def snapshot(self, prices: Dict[str, float]) -> PortfolioSnapshot:
        raw = self._load_state()
        today = date.today().isoformat()
        quantities = {str(k): float(v) for k, v in dict(raw.get("quantities", {})).items()}
        snapshot = PortfolioSnapshot(
            cash=float(raw.get("cash", self.initial_cash)),
            quantities=quantities,
            prices={str(k): float(v) for k, v in prices.items()},
            start_of_day_equity=float(raw.get("start_of_day_equity", 0.0)),
            daily_traded_notional=float(raw.get("daily_traded_notional", 0.0)),
            trading_date=str(raw.get("trading_date", "")),
        )
        if snapshot.trading_date != today:
            snapshot.trading_date = today
            snapshot.start_of_day_equity = snapshot.equity
            snapshot.daily_traded_notional = 0.0
            self._save_snapshot(snapshot)
        return snapshot

    def execute(self, decision: RiskDecision, portfolio: PortfolioSnapshot) -> ExecutionReport:
        order = decision.order
        if not decision.approved:
            return ExecutionReport(
                client_order_id=order.client_order_id,
                ticker=order.ticker,
                side=order.side,
                status="REJECTED",
                filled_quantity=0.0,
                average_price=0.0,
                fee=0.0,
                message="; ".join(decision.reasons),
            )

        market_price = float(portfolio.prices.get(order.ticker, order.reference_price))
        if market_price <= 0.0:
            return self._not_filled(order, "no valid market price")

        if order.order_type == "LIMIT":
            crosses = (
                order.side == "BUY" and float(order.limit_price or 0.0) >= market_price
            ) or (
                order.side == "SELL" and float(order.limit_price or 0.0) <= market_price
            )
            if not crosses:
                return self._not_filled(order, "limit price did not cross the simulated market")
            fill_price = market_price
        else:
            slip = self.slippage_bps / 10_000.0
            fill_price = market_price * (1.0 + slip if order.side == "BUY" else 1.0 - slip)

        quantity = order.quantity
        notional = quantity * fill_price
        fee = notional * self.commission_bps / 10_000.0
        held = float(portfolio.quantities.get(order.ticker, 0.0))
        if order.side == "BUY":
            total_cost = notional + fee
            if total_cost > portfolio.cash + 1e-9:
                return self._not_filled(order, "insufficient paper cash after fees")
            portfolio.cash -= total_cost
            portfolio.quantities[order.ticker] = held + quantity
        else:
            if quantity > held + 1e-9:
                return self._not_filled(order, "insufficient paper holdings")
            portfolio.cash += notional - fee
            remaining = held - quantity
            if remaining <= 1e-9:
                portfolio.quantities.pop(order.ticker, None)
            else:
                portfolio.quantities[order.ticker] = remaining

        portfolio.daily_traded_notional += notional
        self._save_snapshot(portfolio)
        report = ExecutionReport(
            client_order_id=order.client_order_id,
            ticker=order.ticker,
            side=order.side,
            status="FILLED",
            filled_quantity=round(quantity, 6),
            average_price=round(fill_price, 6),
            fee=round(fee, 6),
            broker_order_id=f"paper-{uuid4().hex}",
            message="paper fill",
        )
        self._append_journal(report)
        return report

    def _load_state(self) -> Dict[str, object]:
        if not self.state_path.exists():
            return {"cash": self.initial_cash, "quantities": {}}
        with self.state_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        self.state_directory.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".json.tmp")
        payload = snapshot.to_dict()
        payload.pop("prices", None)
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, self.state_path)

    def _append_journal(self, report: ExecutionReport) -> None:
        self.state_directory.mkdir(parents=True, exist_ok=True)
        value = report.to_dict()
        value["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _not_filled(order, message: str) -> ExecutionReport:
        return ExecutionReport(
            client_order_id=order.client_order_id,
            ticker=order.ticker,
            side=order.side,
            status="NOT_FILLED",
            filled_quantity=0.0,
            average_price=0.0,
            fee=0.0,
            message=message,
        )
