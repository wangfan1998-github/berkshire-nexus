from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.trading.binance_stocks import (
    LIVE_ACKNOWLEDGEMENT,
    BinanceAPIError,
    BinanceStocksClient,
    LiveTradingDisabledError,
    classify_place_ack,
    merge_quote_price,
    summarise_symbol_tradability,
)
from src.trading.live import LiveBroker
from src.trading.risk import DeterministicRiskEngine, RiskPolicy
from src.trading.types import PortfolioSnapshot

from .test_trading import make_order


class FakeClient(BinanceStocksClient):
    """Client whose HTTP layer is replaced by scripted responses."""

    def __init__(self, responses=None, **kwargs):
        kwargs.setdefault("api_key", "key")
        kwargs.setdefault("api_secret", "secret")
        super().__init__(**kwargs)
        self.responses = responses or {}
        self.calls = []

    def _request(self, method, path, *, params=None, signed=False):
        self.calls.append({"method": method, "path": path, "params": params, "signed": signed})
        value = self.responses.get(path)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            return value(params or {})
        if value is None:
            return {}
        return value


class AccountSnapshotTests(unittest.TestCase):
    def test_positions_come_from_wallets_intersected_with_universe(self):
        client = FakeClient({
            "/sapi/v1/equity/market/exchangeInfo": {
                "symbols": [{"symbol": "AAPL"}, {"symbol": "MSFT"}]
            },
            "/sapi/v1/asset/get-funding-asset": [
                {"asset": "USDC", "free": "1500.5", "locked": "0"},
                {"asset": "AAPL", "free": "3", "locked": "1"},
                # Not in the equity universe -> must not become a position.
                {"asset": "BTC", "free": "0.5", "locked": "0"},
            ],
            "/sapi/v3/asset/getUserAsset": [
                {"asset": "MSFT", "free": "2", "locked": "0"},
            ],
        })
        snapshot = client.account_snapshot()

        self.assertAlmostEqual(snapshot["cash"], 1500.5)
        tickers = [item["ticker"] for item in snapshot["positions"]]
        self.assertEqual(tickers, ["AAPL", "MSFT"])
        apple = snapshot["positions"][0]
        # free + locked, so pledged shares are not silently dropped.
        self.assertAlmostEqual(apple["quantity"], 4.0)
        self.assertAlmostEqual(apple["locked"], 1.0)
        self.assertEqual([item["asset"] for item in snapshot["unclassified_assets"]], ["BTC"])

    def test_account_snapshot_requires_secret(self):
        client = FakeClient(api_secret="")
        with self.assertRaises(ValueError):
            client.account_snapshot()

    def test_wallet_failure_is_reported_not_raised(self):
        client = FakeClient({
            "/sapi/v1/equity/market/exchangeInfo": {"symbols": []},
            "/sapi/v1/asset/get-funding-asset": BinanceAPIError(-1121, "bad", 400),
            "/sapi/v3/asset/getUserAsset": [{"asset": "USDC", "free": "10", "locked": "0"}],
        })
        snapshot = client.account_snapshot()
        self.assertIn("CARD", snapshot["wallet_errors"])
        self.assertAlmostEqual(snapshot["cash"], 10.0)


class AckAndHelperTests(unittest.TestCase):
    def test_place_ack_s_is_acceptance_not_a_fill(self):
        ack = classify_place_ack({"status": "S", "orderId": "o-1"})
        self.assertTrue(ack["accepted"])
        self.assertEqual(ack["order_id"], "o-1")
        self.assertFalse(classify_place_ack({"status": "F"})["accepted"])

    def test_tradability_gates(self):
        self.assertTrue(summarise_symbol_tradability({"tradability": "BUY_SELL"})["allows_buy"])
        self.assertFalse(summarise_symbol_tradability({"tradability": "SELL"})["allows_buy"])
        self.assertTrue(summarise_symbol_tradability({"tradability": "NONE"})["halted"])

    def test_quote_price_falls_back_to_mid(self):
        self.assertAlmostEqual(merge_quote_price({"bidPrice": "10", "askPrice": "12"}), 11.0)
        self.assertAlmostEqual(merge_quote_price({"data": [{"lastPrice": "5.5"}]}), 5.5)
        self.assertEqual(merge_quote_price({}), 0.0)

    def test_normalise_order_derives_average_from_quote_qty(self):
        row = {"symbol": "AAPL", "status": "FILLED", "executedQty": "2", "cummulativeQuoteQty": "300"}
        normalised = BinanceStocksClient.normalise_order(row)
        self.assertAlmostEqual(normalised["average_price"], 150.0)
        self.assertTrue(BinanceStocksClient.is_terminal_status(normalised["status"]))


class LiveBrokerTests(unittest.TestCase):
    def setUp(self):
        self.portfolio = PortfolioSnapshot(
            cash=10_000.0,
            quantities={},
            prices={"AAPL": 100.0},
            start_of_day_equity=10_000.0,
            trading_date="2026-08-27",
        )
        self.engine = DeterministicRiskEngine(RiskPolicy(max_single_order_notional=5_000.0))

    def _approved(self):
        # Live BUYs additionally require broker-authoritative pricing, which the
        # live cycle sets once Binance's own quote confirms the price.
        decision = self.engine.evaluate(
            make_order(data_is_authoritative=True), self.portfolio, mode="live"
        )
        self.assertTrue(decision.approved, decision.reasons)
        return decision

    def test_live_buy_needs_broker_authoritative_price(self):
        """Third-party research prices must never reach the live market."""

        decision = self.engine.evaluate(
            make_order(data_is_authoritative=False), self.portfolio, mode="live"
        )
        self.assertFalse(decision.approved)
        self.assertIn(
            "third-party research data is not broker-authoritative for live execution",
            decision.reasons,
        )

    def test_submission_blocked_without_environment_acknowledgement(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(allow_live_orders=True)
            broker = LiveBroker(client, directory)
            report = broker.execute(self._approved(), self.portfolio)
            self.assertEqual(report.status, "REJECTED")
            # Nothing may be left pending if the order never left the process.
            self.assertFalse(broker.has_unresolved_orders())

    def test_accepted_order_is_working_not_filled(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(
                {"/sapi/v1/equity/order/place": {"status": "S", "orderId": "o-9"}},
                allow_live_orders=True,
            )
            broker = LiveBroker(client, directory)
            with patch.dict(os.environ, {"BERKSHIRE_NEXUS_LIVE_TRADING": LIVE_ACKNOWLEDGEMENT}):
                report = broker.execute(self._approved(), self.portfolio)
            self.assertEqual(report.status, "ACCEPTED")
            self.assertEqual(report.filled_quantity, 0.0)
            self.assertTrue(broker.has_unresolved_orders())

    def test_halted_symbol_is_rejected_before_any_network_call(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(allow_live_orders=True)
            broker = LiveBroker(client, directory)
            with patch.dict(os.environ, {"BERKSHIRE_NEXUS_LIVE_TRADING": LIVE_ACKNOWLEDGEMENT}):
                report = broker.execute(
                    self._approved(), self.portfolio, tradability={"tradability": "NONE"}
                )
            self.assertEqual(report.status, "REJECTED")
            self.assertEqual(client.calls, [])

    def test_ambiguous_network_failure_is_quarantined_for_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(
                {"/sapi/v1/equity/order/place": BinanceAPIError("network", "timeout", None)},
                allow_live_orders=True,
            )
            broker = LiveBroker(client, directory)
            with patch.dict(os.environ, {"BERKSHIRE_NEXUS_LIVE_TRADING": LIVE_ACKNOWLEDGEMENT}):
                report = broker.execute(self._approved(), self.portfolio)
            # Must NOT be reported as rejected: the order may have reached Binance.
            self.assertEqual(report.status, "UNKNOWN")
            self.assertTrue(broker.has_unresolved_orders())

    def test_reconcile_settles_filled_order_and_clears_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(
                {
                    "/sapi/v1/equity/order/place": {"status": "S", "orderId": "o-1"},
                    "/sapi/v1/equity/order/detail": {
                        "symbol": "AAPL",
                        "side": "BUY",
                        "status": "FILLED",
                        "executedQty": "10",
                        "avgPrice": "100.05",
                        "fee": "0.1",
                        "orderId": "o-1",
                    },
                },
                allow_live_orders=True,
            )
            broker = LiveBroker(client, directory)
            with patch.dict(os.environ, {"BERKSHIRE_NEXUS_LIVE_TRADING": LIVE_ACKNOWLEDGEMENT}):
                broker.execute(self._approved(), self.portfolio)
            summary = broker.reconcile()

            self.assertEqual(len(summary["settled"]), 1)
            self.assertEqual(summary["settled"][0]["status"], "FILLED")
            self.assertAlmostEqual(summary["settled"][0]["filled_quantity"], 10.0)
            self.assertFalse(broker.has_unresolved_orders())
            journal = Path(directory) / "live_executions.jsonl"
            rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
            self.assertTrue(any(row["status"] == "FILLED" for row in rows))
            self.assertTrue(all(row["mode"] == "live" for row in rows))

    def test_reconcile_keeps_working_order_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(
                {
                    "/sapi/v1/equity/order/place": {"status": "S", "orderId": "o-2"},
                    "/sapi/v1/equity/order/detail": {
                        "symbol": "AAPL", "side": "BUY", "status": "ACCEPTED", "executedQty": "0",
                    },
                },
                allow_live_orders=True,
            )
            broker = LiveBroker(client, directory)
            with patch.dict(os.environ, {"BERKSHIRE_NEXUS_LIVE_TRADING": LIVE_ACKNOWLEDGEMENT}):
                broker.execute(self._approved(), self.portfolio)
            summary = broker.reconcile()
            self.assertEqual(len(summary["still_open"]), 1)
            self.assertTrue(broker.has_unresolved_orders())

    def test_live_portfolio_is_built_from_exchange_balances(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient({
                "/sapi/v1/equity/market/exchangeInfo": {"symbols": [{"symbol": "AAPL"}]},
                "/sapi/v1/asset/get-funding-asset": [
                    {"asset": "USDC", "free": "2000", "locked": "0"},
                    {"asset": "AAPL", "free": "5", "locked": "0"},
                ],
                "/sapi/v3/asset/getUserAsset": [],
            })
            broker = LiveBroker(client, directory)
            portfolio = broker.live_portfolio({"AAPL": 200.0})
            self.assertAlmostEqual(portfolio.cash, 2000.0)
            self.assertAlmostEqual(portfolio.quantities["AAPL"], 5.0)
            self.assertAlmostEqual(portfolio.equity, 3000.0)
            # A cold start must not trip the daily-loss kill switch.
            self.assertAlmostEqual(portfolio.start_of_day_equity, portfolio.equity)

    def test_cancel_requires_live_gate(self):
        client = FakeClient(allow_live_orders=False)
        with self.assertRaises(LiveTradingDisabledError):
            client.cancel_order("o-1")


if __name__ == "__main__":
    unittest.main()
