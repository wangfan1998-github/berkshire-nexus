"""Live Binance Stocks broker with restart-safe order recovery and reconciliation.

Design rules which the paper broker does not need:

1. **Intent is journalled before the network call.** If the process dies between
   submitting and recording, the pending-order file still names the order, so
   recovery can ask Binance what happened instead of guessing.
2. **An ack is not a fill.** ``/order/place`` returns ``S``/``F`` only. Positions
   come from Binance, never from local arithmetic on an ack.
3. **Ambiguous failures are quarantined, not retried.** A network error on a POST
   may still have reached the exchange, so the order is marked ``UNKNOWN`` and
   left for reconciliation.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .binance_stocks import (
    BinanceAPIError,
    BinanceStocksClient,
    LiveTradingDisabledError,
    classify_place_ack,
    summarise_symbol_tradability,
)
from .types import ExecutionReport, PortfolioSnapshot, RiskDecision


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LiveBroker:
    """Submits approved orders to Binance and reconciles them against the API."""

    def __init__(
        self,
        client: BinanceStocksClient,
        state_directory: Union[Path, str],
    ):
        self.client = client
        self.state_directory = Path(state_directory)
        self.pending_path = self.state_directory / "live_pending_orders.json"
        self.journal_path = self.state_directory / "live_executions.jsonl"
        self.recovery_path = self.state_directory / "live_recovery.json"

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def execute(
        self,
        decision: RiskDecision,
        portfolio: PortfolioSnapshot,
        *,
        tradability: Optional[Dict[str, Any]] = None,
    ) -> ExecutionReport:
        order = decision.order
        if not decision.approved:
            return self._report(order, "REJECTED", message="; ".join(decision.reasons))

        # Halted or one-way symbols must be filtered before spending an API call.
        if tradability is not None:
            gate = summarise_symbol_tradability(tradability)
            if order.side == "BUY" and not gate["allows_buy"]:
                return self._report(
                    order, "REJECTED", message=f"symbol not buyable (tradability={gate['tradability']})"
                )
            if order.side == "SELL" and not gate["allows_sell"]:
                return self._report(
                    order, "REJECTED", message=f"symbol not sellable (tradability={gate['tradability']})"
                )

        # Record intent BEFORE the network call so a crash is recoverable.
        self._track_pending(order.to_dict())

        try:
            payload = self.client.place_order(order)
        except LiveTradingDisabledError as error:
            self._drop_pending(order.client_order_id)
            return self._report(order, "REJECTED", message=str(error))
        except BinanceAPIError as error:
            if error.status is None or error.code == "network":
                # Ambiguous: the exchange may have accepted it. Keep it pending.
                self._mark_pending(order.client_order_id, "UNKNOWN", str(error))
                report = self._report(
                    order, "UNKNOWN", message=f"submission outcome unknown, pending reconciliation: {error}"
                )
                self._append_journal(report)
                return report
            self._drop_pending(order.client_order_id)
            return self._report(order, "REJECTED", message=str(error))
        except ValueError as error:
            self._drop_pending(order.client_order_id)
            return self._report(order, "REJECTED", message=str(error))

        ack = classify_place_ack(payload)
        if not ack["accepted"]:
            self._drop_pending(order.client_order_id)
            report = self._report(
                order, "REJECTED", message=f"exchange rejected the order (ack={ack['ack'] or 'unknown'})"
            )
            self._append_journal(report)
            return report

        self._mark_pending(
            order.client_order_id,
            "ACCEPTED",
            "accepted by exchange",
            order_id=ack["order_id"],
        )
        # ACCEPTED means working, not filled. Fills arrive via reconciliation.
        report = self._report(
            order,
            "ACCEPTED",
            broker_order_id=ack["order_id"] or None,
            message="working at exchange; awaiting fill reconciliation",
        )
        self._append_journal(report)
        return report

    # ------------------------------------------------------------------
    # Reconciliation and recovery
    # ------------------------------------------------------------------

    def reconcile(self) -> Dict[str, Any]:
        """Resolve every tracked order against the exchange.

        Safe to call on startup: this is what makes a mid-flight restart
        recoverable.
        """

        pending = self._load_pending()
        if not pending:
            return {"checked": 0, "settled": [], "still_open": [], "unresolved": []}

        settled: List[Dict[str, Any]] = []
        still_open: List[Dict[str, Any]] = []
        unresolved: List[Dict[str, Any]] = []

        for client_order_id, record in list(pending.items()):
            try:
                detail = self.client.order_detail(client_order_id=client_order_id)
            except (BinanceAPIError, ValueError) as error:
                # An UNKNOWN order missing from the exchange never landed.
                if isinstance(error, BinanceAPIError) and error.status == 400:
                    unresolved.append({
                        "client_order_id": client_order_id,
                        "reason": f"not found at exchange: {error}",
                        "assumed": "never_submitted",
                    })
                    self._drop_pending(client_order_id)
                    continue
                unresolved.append({"client_order_id": client_order_id, "reason": str(error)})
                continue

            normalised = self.client.normalise_order(detail if isinstance(detail, dict) else {})
            status = normalised["status"]
            if not status:
                unresolved.append({
                    "client_order_id": client_order_id,
                    "reason": "exchange response carried no status field",
                    "raw": normalised["raw"],
                })
                continue

            if self.client.is_terminal_status(status):
                report = ExecutionReport(
                    client_order_id=client_order_id,
                    ticker=normalised["ticker"] or str(record.get("ticker", "")),
                    side=normalised["side"] or str(record.get("side", "")),
                    status=status,
                    filled_quantity=normalised["filled_quantity"],
                    average_price=normalised["average_price"],
                    fee=normalised["fee"],
                    broker_order_id=normalised["order_id"] or None,
                    message="reconciled from exchange",
                )
                self._append_journal(report)
                self._drop_pending(client_order_id)
                settled.append(report.to_dict())
            else:
                self._mark_pending(client_order_id, status, "still working at exchange")
                still_open.append({
                    "client_order_id": client_order_id,
                    "status": status,
                    "filled_quantity": normalised["filled_quantity"],
                    "ticker": normalised["ticker"],
                })

        summary = {
            "reconciled_at_utc": _now(),
            "checked": len(pending),
            "settled": settled,
            "still_open": still_open,
            "unresolved": unresolved,
        }
        self._write_json(self.recovery_path, summary)
        return summary

    def account_state(self) -> Dict[str, Any]:
        """Authoritative portfolio straight from Binance (never local state)."""

        snapshot = self.client.account_snapshot()
        snapshot["fetched_at_utc"] = _now()
        return snapshot

    def live_portfolio(self, prices: Dict[str, float]) -> PortfolioSnapshot:
        """Build a risk-engine-compatible snapshot from real balances."""

        state = self.account_state()
        quantities = {
            str(position["ticker"]): float(position["quantity"])
            for position in state.get("positions", [])
            if float(position.get("quantity", 0.0)) > 0.0
        }
        resolved = {ticker: float(prices.get(ticker, 0.0)) for ticker in quantities}
        snapshot = PortfolioSnapshot(
            cash=float(state.get("cash", 0.0)),
            quantities=quantities,
            prices=resolved,
        )
        # No authoritative intraday baseline exists on a cold start; using current
        # equity keeps the daily-loss kill switch from firing spuriously.
        snapshot.start_of_day_equity = snapshot.equity
        snapshot.trading_date = datetime.now(timezone.utc).date().isoformat()
        return snapshot

    def cancel_all_open(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        result = self.client.cancel_all(symbol)
        return {"cancelled_at_utc": _now(), "symbol": symbol, "response": result}

    def open_orders(self) -> List[Dict[str, Any]]:
        return [self.client.normalise_order(row) for row in self.client.open_orders()]

    def has_unresolved_orders(self) -> bool:
        return bool(self._load_pending())

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_pending(self) -> Dict[str, Any]:
        if not self.pending_path.exists():
            return {}
        try:
            with self.pending_path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            return dict(value) if isinstance(value, dict) else {}
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return {}

    def _track_pending(self, order: Dict[str, Any]) -> None:
        pending = self._load_pending()
        pending[str(order["client_order_id"])] = {
            "submitted_at_utc": _now(),
            "state": "SUBMITTING",
            "ticker": order.get("ticker"),
            "side": order.get("side"),
            "quantity": order.get("quantity"),
            "limit_price": order.get("limit_price"),
            "analysis_id": order.get("analysis_id"),
        }
        self._write_json(self.pending_path, pending)

    def _mark_pending(
        self,
        client_order_id: str,
        state: str,
        message: str,
        *,
        order_id: str = "",
    ) -> None:
        pending = self._load_pending()
        record = dict(pending.get(client_order_id, {}))
        record.update({"state": state, "message": message, "updated_at_utc": _now()})
        if order_id:
            record["order_id"] = order_id
        pending[client_order_id] = record
        self._write_json(self.pending_path, pending)

    def _drop_pending(self, client_order_id: str) -> None:
        pending = self._load_pending()
        if pending.pop(client_order_id, None) is not None:
            self._write_json(self.pending_path, pending)

    def _write_json(self, path: Path, payload: Any) -> None:
        self.state_directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, path)

    def _append_journal(self, report: ExecutionReport) -> None:
        self.state_directory.mkdir(parents=True, exist_ok=True)
        value = report.to_dict()
        value["recorded_at_utc"] = _now()
        value["mode"] = "live"
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _report(
        order,
        status: str,
        *,
        broker_order_id: Optional[str] = None,
        message: str = "",
    ) -> ExecutionReport:
        return ExecutionReport(
            client_order_id=order.client_order_id,
            ticker=order.ticker,
            side=order.side,
            status=status,
            filled_quantity=0.0,
            average_price=0.0,
            fee=0.0,
            broker_order_id=broker_order_id,
            message=message,
        )
