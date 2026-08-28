from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.trading.binance_stocks import (
    LIVE_ACKNOWLEDGEMENT,
    BinanceStocksClient,
    LiveTradingDisabledError,
)
from src.trading.paper import PaperBroker
from src.trading.planner import AllocationPlanner
from src.trading.risk import DeterministicRiskEngine, RiskPolicy
from src.trading.types import OrderIntent, PortfolioSnapshot


def make_order(**overrides) -> OrderIntent:
    values = {
        "client_order_id": "bn" + "1" * 32,
        "ticker": "AAPL",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 10.0,
        "notional": 1_000.0,
        "reference_price": 100.0,
        "limit_price": 100.10,
        "trading_session": "RTH",
        "time_in_force": "DAY",
        "target_weight": 0.10,
        "analysis_position_cap_pct": 10.0,
        "analysis_score": 80.0,
        "learned_score": None,
        "combined_score": 80.0,
        "analysis_id": "analysis-1",
        "data_source": "fixture",
        "uses_fallback_data": False,
        "tokenize": False,
        "rationale": "test",
    }
    values.update(overrides)
    return OrderIntent(**values)


class RiskAndPaperTests(unittest.TestCase):
    def setUp(self):
        self.portfolio = PortfolioSnapshot(
            cash=10_000.0,
            quantities={},
            prices={"AAPL": 100.0},
            start_of_day_equity=10_000.0,
            daily_traded_notional=0.0,
            trading_date="2026-08-26",
        )
        self.engine = DeterministicRiskEngine(RiskPolicy(max_single_order_notional=2_000.0))

    def test_live_buy_rejects_fallback_data(self):
        decision = self.engine.evaluate(make_order(uses_fallback_data=True), self.portfolio, mode="live")
        self.assertFalse(decision.approved)
        self.assertIn("分析数据来自回退/推断值，不能触发实盘下单", decision.reasons)

    def test_live_buy_rejects_complete_but_non_authoritative_research_data(self):
        decision = self.engine.evaluate(
            make_order(uses_fallback_data=False, data_is_authoritative=False),
            self.portfolio,
            mode="live",
        )
        self.assertFalse(decision.approved)
        self.assertIn(
            "价格非券商权威来源，实盘拒绝执行",
            decision.reasons,
        )

    def test_risk_reducing_sell_is_allowed_below_score(self):
        portfolio = PortfolioSnapshot(
            cash=0.0,
            quantities={"AAPL": 10.0},
            prices={"AAPL": 100.0},
            start_of_day_equity=1_000.0,
            daily_traded_notional=1_000.0,
            trading_date="2026-08-26",
        )
        order = make_order(side="SELL", combined_score=10.0, uses_fallback_data=True)
        decision = self.engine.evaluate(order, portfolio, mode="live")
        self.assertTrue(decision.approved, decision.reasons)

    def test_paper_broker_persists_fill(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = PaperBroker(directory, initial_cash=10_000.0)
            portfolio = broker.snapshot({"AAPL": 100.0})
            decision = self.engine.evaluate(make_order(), portfolio, mode="paper")
            report = broker.execute(decision, portfolio)
            self.assertEqual(report.status, "FILLED")
            reloaded = broker.snapshot({"AAPL": 100.0})
            self.assertAlmostEqual(reloaded.quantities["AAPL"], 10.0)
            self.assertLess(reloaded.cash, 9_000.0)
            self.assertTrue((Path(directory) / "paper_executions.jsonl").exists())


class PlannerTests(unittest.TestCase):
    @staticmethod
    def report(score: float, cap: float = 10.0):
        return SimpleNamespace(
            financials=SimpleNamespace(
                ticker="AAPL",
                price=100.0,
                data_source="fixture",
                uses_fallback_data=False,
            ),
            risk_assessment=SimpleNamespace(recommended_max_allocation_pct=cap),
            final_composite_score=score,
            analysis_id="analysis-1",
        )

    def test_low_score_existing_position_is_planned_for_exit(self):
        portfolio = PortfolioSnapshot(
            cash=9_000.0,
            quantities={"AAPL": 10.0},
            prices={"AAPL": 100.0},
            start_of_day_equity=10_000.0,
            trading_date="2026-08-26",
        )
        orders = AllocationPlanner().plan([self.report(40.0)], portfolio)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].side, "SELL")
        self.assertEqual(orders[0].target_weight, 0.0)


class BinanceAdapterTests(unittest.TestCase):
    def test_live_orders_require_two_independent_gates(self):
        client = BinanceStocksClient("key", "secret", allow_live_orders=False)
        with self.assertRaises(LiveTradingDisabledError):
            client.place_order(make_order())

    def test_limit_order_payload_forces_direct_equity(self):
        captured = {}

        class RecordingClient(BinanceStocksClient):
            def _request(self, method, path, *, params=None, signed=False):
                captured.update({"method": method, "path": path, "params": params, "signed": signed})
                return {"status": "S", "orderId": "fixture"}

        client = RecordingClient("key", "secret", allow_live_orders=True)
        with patch.dict(os.environ, {"BERKSHIRE_NEXUS_LIVE_TRADING": LIVE_ACKNOWLEDGEMENT}):
            response = client.place_order(make_order())
        self.assertEqual(response["status"], "S")
        self.assertEqual(captured["path"], "/sapi/v1/equity/order/place")
        self.assertEqual(captured["params"]["tokenize"], "false")
        self.assertEqual(captured["params"]["tradingSession"], "RTH")
        self.assertTrue(captured["signed"])


if __name__ == "__main__":
    unittest.main()
