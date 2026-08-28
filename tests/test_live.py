from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.trading.binance_stocks import (
    classify_wallet_asset,
    LIVE_ACKNOWLEDGEMENT,
    BinanceAPIError,
    BinanceStocksClient,
    LiveTradingDisabledError,
    classify_place_ack,
    MAX_TRUSTED_SPREAD_PCT,
    merge_quote_price,
    quote_spread_pct,
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


class AssetClassificationTests(unittest.TestCase):
    """Wallet-asset -> ticker resolution must be account-agnostic."""

    RESOLUTION = {
        "AAPLB": {"ticker": "AAPL", "multiplier": 1.00060391, "multiplier_valid": True},
        "MUB": {"ticker": "MU", "multiplier": 1.00010751, "multiplier_valid": True},
    }
    UNIVERSE = {"AAPL", "MU", "MUB", "GOOGL", "U"}

    def test_tokenized_map_outranks_a_universe_name_collision(self):
        """MUB is Micron tokenized, and also a real ETF ticker.

        Without the API mapping taking precedence, a tokenized Micron holding
        would be booked as the MUB ETF at the wrong price.
        """

        resolved = classify_wallet_asset("MUB", self.RESOLUTION, self.UNIVERSE)
        self.assertEqual(resolved["ticker"], "MU")
        self.assertEqual(resolved["resolved_by"], "tokenized-assets")
        self.assertTrue(resolved["tokenized"])

    def test_tokenized_asset_resolves_via_api_not_a_suffix_guess(self):
        resolved = classify_wallet_asset("AAPLB", self.RESOLUTION, self.UNIVERSE)
        self.assertEqual(resolved["ticker"], "AAPL")
        self.assertAlmostEqual(resolved["multiplier"], 1.00060391)

    def test_eq_prefix_resolves_without_any_api_data(self):
        resolved = classify_wallet_asset("EQ_GOOGL", {}, set())
        self.assertEqual(resolved["ticker"], "GOOGL")
        self.assertEqual(resolved["resolved_by"], "eq-prefix")

    def test_bare_ticker_is_never_accepted_on_a_universe_match_alone(self):
        """Regression: crypto token U (~$1) collides with Unity stock (~$44).

        The equity universe lists ~7,900 symbols, so short crypto tickers
        collide with real ones. A universe match alone mispriced a crypto
        balance 44x, so it is no longer sufficient evidence.
        """

        self.assertIsNone(classify_wallet_asset("U", {}, self.UNIVERSE))
        self.assertIsNone(classify_wallet_asset("U", {}, self.UNIVERSE, {"stockTicker": None}))

    def test_wallet_stock_ticker_is_the_strongest_evidence(self):
        """Equity rows carry stockTicker; crypto rows return null."""

        resolved = classify_wallet_asset("EQ_AVGO", {}, set(), {"stockTicker": "AVGO"})
        self.assertEqual(resolved["ticker"], "AVGO")
        self.assertEqual(resolved["resolved_by"], "wallet-stockTicker")

    def test_crypto_is_never_classified_as_equity(self):
        for asset in ("BTC", "ETH", "SENT", "SOL"):
            self.assertIsNone(classify_wallet_asset(asset, self.RESOLUTION, self.UNIVERSE))

    def test_unknown_suffix_b_asset_is_not_guessed(self):
        """A B-suffixed asset absent from the map must not be assumed tokenized."""

        self.assertIsNone(classify_wallet_asset("FOOB", {}, {"FOO"}))


class TokenizedPositionTests(unittest.TestCase):
    def test_tokenized_balance_is_scaled_to_share_equivalent(self):
        client = FakeClient({
            "/sapi/v1/equity/market/exchangeInfo": {"symbols": [{"symbol": "AAPL"}]},
            "/sapi/v1/equity/market/tokenized-assets": [
                {
                    "assetCode": "AAPLB",
                    "underlyingEquitySymbol": "AAPL",
                    "multiplier": "2",
                    "multiplierValid": True,
                }
            ],
            "/sapi/v1/asset/get-funding-asset": [
                {"asset": "AAPLB", "free": "3", "locked": "0"},
            ],
            "/sapi/v3/asset/getUserAsset": [],
        })
        snapshot = client.account_snapshot()
        position = snapshot["positions"][0]
        self.assertEqual(position["ticker"], "AAPL")
        # 3 tokens x multiplier 2 = 6 share-equivalents.
        self.assertAlmostEqual(position["quantity"], 6.0)
        self.assertTrue(position["tokenized"])

    def test_invalid_multiplier_falls_back_to_one(self):
        """A stale multiplier must not silently scale a real position."""

        client = FakeClient({
            "/sapi/v1/equity/market/exchangeInfo": {"symbols": [{"symbol": "AAPL"}]},
            "/sapi/v1/equity/market/tokenized-assets": [
                {
                    "assetCode": "AAPLB",
                    "underlyingEquitySymbol": "AAPL",
                    "multiplier": "7",
                    "multiplierValid": False,
                }
            ],
            "/sapi/v1/asset/get-funding-asset": [
                {"asset": "AAPLB", "free": "3", "locked": "0"},
            ],
            "/sapi/v3/asset/getUserAsset": [],
        })
        position = client.account_snapshot()["positions"][0]
        self.assertAlmostEqual(position["quantity"], 3.0)

    def test_direct_and_tokenized_holdings_merge_into_one_ticker(self):
        client = FakeClient({
            "/sapi/v1/equity/market/exchangeInfo": {"symbols": [{"symbol": "AAPL"}]},
            "/sapi/v1/equity/market/tokenized-assets": [
                {
                    "assetCode": "AAPLB",
                    "underlyingEquitySymbol": "AAPL",
                    "multiplier": "1",
                    "multiplierValid": True,
                }
            ],
            "/sapi/v1/asset/get-funding-asset": [
                {"asset": "EQ_AAPL", "free": "2", "locked": "0"},
                {"asset": "AAPLB", "free": "1", "locked": "0"},
            ],
            "/sapi/v3/asset/getUserAsset": [],
        })
        snapshot = client.account_snapshot()
        self.assertEqual(len(snapshot["positions"]), 1)
        position = snapshot["positions"][0]
        self.assertAlmostEqual(position["quantity"], 3.0)
        self.assertEqual(sorted(position["wallet_assets"]), ["AAPLB", "EQ_AAPL"])

    def test_tokenized_endpoint_failure_does_not_break_direct_holdings(self):
        client = FakeClient({
            "/sapi/v1/equity/market/exchangeInfo": {"symbols": [{"symbol": "TSM"}]},
            "/sapi/v1/equity/market/tokenized-assets": BinanceAPIError(-1121, "down", 400),
            "/sapi/v1/asset/get-funding-asset": [
                {"asset": "EQ_TSM", "free": "0.95", "locked": "0"},
            ],
            "/sapi/v3/asset/getUserAsset": [],
        })
        snapshot = client.account_snapshot()
        self.assertEqual([p["ticker"] for p in snapshot["positions"]], ["TSM"])
        self.assertEqual(snapshot["tokenized_map_size"], 0)


class AccountSnapshotTests(unittest.TestCase):
    def test_eq_prefixed_wallet_assets_are_recognised_as_positions(self):
        """Wallet rows are EQ_<TICKER>; exchangeInfo returns the bare ticker.

        Regression: intersecting the raw wallet asset name against the universe
        discarded every real stock holding and reported a near-empty portfolio.
        """

        client = FakeClient({
            "/sapi/v1/equity/market/exchangeInfo": {
                "symbols": [{"symbol": "AVGO"}, {"symbol": "GOOGL"}, {"symbol": "QQQM"}]
            },
            "/sapi/v1/asset/get-funding-asset": [
                {"asset": "EQ_AVGO", "free": "0.93578113", "locked": "0"},
                {"asset": "EQ_GOOGL", "free": "1.18", "locked": "0"},
                {"asset": "EQ_QQQM", "free": "4.77290262", "locked": "0"},
                {"asset": "USDC", "free": "0.027396", "locked": "0"},
            ],
            "/sapi/v3/asset/getUserAsset": [],
        })
        snapshot = client.account_snapshot()

        self.assertEqual(
            [item["ticker"] for item in snapshot["positions"]], ["AVGO", "GOOGL", "QQQM"]
        )
        self.assertEqual(snapshot["unclassified_assets"], [])
        self.assertAlmostEqual(snapshot["positions"][0]["quantity"], 0.93578113)
        # The originating wallet asset names are retained for traceability.
        self.assertEqual(snapshot["positions"][0]["wallet_assets"], ["EQ_AVGO"])

    def test_eq_prefix_is_trusted_when_universe_lookup_fails(self):
        """An EQ_ prefix alone proves an equity holding."""

        client = FakeClient({
            "/sapi/v1/equity/market/exchangeInfo": BinanceAPIError(-1121, "down", 400),
            "/sapi/v1/asset/get-funding-asset": [
                {"asset": "EQ_TSM", "free": "0.95795238", "locked": "0"},
            ],
            "/sapi/v3/asset/getUserAsset": [],
        })
        snapshot = client.account_snapshot()
        self.assertEqual([item["ticker"] for item in snapshot["positions"]], ["TSM"])

    def test_crypto_without_prefix_is_not_a_position(self):
        client = FakeClient({
            "/sapi/v1/equity/market/exchangeInfo": {"symbols": [{"symbol": "AAPL"}]},
            "/sapi/v1/asset/get-funding-asset": [
                {"asset": "BTC", "free": "0.5", "locked": "0"},
                {"asset": "USD1", "free": "0.00002918", "locked": "0"},
            ],
            "/sapi/v3/asset/getUserAsset": [],
        })
        snapshot = client.account_snapshot()
        self.assertEqual(snapshot["positions"], [])
        self.assertEqual([item["asset"] for item in snapshot["unclassified_assets"]], ["BTC"])
        # USD1 is settlement cash, not an unclassified asset.
        self.assertIn("USD1", snapshot["cash_by_asset"])

    def test_positions_come_from_wallets_intersected_with_universe(self):
        client = FakeClient({
            "/sapi/v1/equity/market/exchangeInfo": {
                "symbols": [{"symbol": "AAPL"}, {"symbol": "MSFT"}]
            },
            "/sapi/v1/asset/get-funding-asset": [
                {"asset": "USDC", "free": "1500.5", "locked": "0"},
                {"asset": "EQ_AAPL", "stockTicker": "AAPL", "free": "3", "locked": "1"},
                # No stockTicker and no EQ_ prefix -> not an equity position.
                {"asset": "BTC", "free": "0.5", "locked": "0"},
            ],
            "/sapi/v3/asset/getUserAsset": [
                {"asset": "EQ_MSFT", "stockTicker": "MSFT", "free": "2", "locked": "0"},
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

    def test_wide_spread_is_detectable_by_callers(self):
        """A wide book still mids, but callers must be able to see it is wide.

        Binance's equity quote has no last-traded price, so every figure from it
        is an estimate. Measured against Yahoo across 8 live holdings, mean
        absolute error was midpoint 1.33%, ask 1.62%, bid 1.80% — so the midpoint
        stays, and a wide spread is surfaced rather than swapped for the bid.
        """

        wide = {"bidPrice": "570.11", "askPrice": "599.99"}
        self.assertAlmostEqual(merge_quote_price(wide), 585.05)
        self.assertGreater(quote_spread_pct(wide), MAX_TRUSTED_SPREAD_PCT)

        tight = {"bidPrice": "296.13", "askPrice": "296.17"}
        self.assertAlmostEqual(merge_quote_price(tight), 296.15)
        self.assertLess(quote_spread_pct(tight), MAX_TRUSTED_SPREAD_PCT)

    def test_single_sided_book_still_yields_a_price(self):
        self.assertAlmostEqual(merge_quote_price({"bidPrice": "10"}), 10.0)
        self.assertAlmostEqual(merge_quote_price({"askPrice": "12"}), 12.0)

    def test_quote_price_falls_back_to_mid(self):
        self.assertAlmostEqual(merge_quote_price({"bidPrice": "10", "askPrice": "12"}), 11.0)
        self.assertAlmostEqual(merge_quote_price({"bidPrice": "10.00", "askPrice": "10.05"}), 10.025)
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
            "价格非券商权威来源，实盘拒绝执行",
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
                    {"asset": "EQ_AAPL", "stockTicker": "AAPL", "free": "5", "locked": "0"},
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

    def test_live_portfolio_prices_holdings_outside_the_analysis_universe(self):
        """Every held position must be priced, not only analysed ones.

        Regression: prices came solely from the analysis universe, so holdings
        outside it were valued at 0. Equity collapsed from ~$5,000 to ~$400 and
        the planner tried to liquidate 94% of a sound position to reach a 6%
        target weight computed against the wrong denominator.
        """

        quote_calls = []

        class PricingClient(FakeClient):
            def latest_quote(self, symbol):
                quote_calls.append(symbol)
                return {"price": {"AVGO": "360.0", "QQQM": "295.0"}.get(symbol.upper(), "0")}

        with tempfile.TemporaryDirectory() as directory:
            client = PricingClient({
                "/sapi/v1/equity/market/exchangeInfo": {
                    "symbols": [{"symbol": "AVGO"}, {"symbol": "QQQM"}, {"symbol": "TSM"}]
                },
                "/sapi/v1/asset/get-funding-asset": [
                    {"asset": "USDC", "free": "10", "locked": "0"},
                    {"asset": "EQ_AVGO", "free": "1", "locked": "0"},
                    {"asset": "EQ_QQQM", "free": "2", "locked": "0"},
                ],
                "/sapi/v3/asset/getUserAsset": [],
            })
            broker = LiveBroker(client, directory)
            # Only TSM is in the analysis universe; it is not even held.
            portfolio = broker.live_portfolio({"TSM": 424.0})

            self.assertAlmostEqual(portfolio.prices["AVGO"], 360.0)
            self.assertAlmostEqual(portfolio.prices["QQQM"], 295.0)
            # 10 cash + 360 + 590 = 960, not 10.
            self.assertAlmostEqual(portfolio.equity, 960.0)
            self.assertEqual(broker.unpriced_positions, [])
            self.assertEqual(sorted(quote_calls), ["AVGO", "QQQM"])

    def test_unpriceable_holding_is_reported_not_treated_as_zero(self):
        class SilentClient(FakeClient):
            def latest_quote(self, symbol):
                return {}

        with tempfile.TemporaryDirectory() as directory:
            client = SilentClient({
                "/sapi/v1/equity/market/exchangeInfo": {"symbols": [{"symbol": "AVGO"}]},
                "/sapi/v1/asset/get-funding-asset": [
                    {"asset": "EQ_AVGO", "free": "1", "locked": "0"},
                ],
                "/sapi/v3/asset/getUserAsset": [],
            })
            broker = LiveBroker(client, directory)
            broker.live_portfolio({})
            self.assertEqual(broker.unpriced_positions, ["AVGO"])

    def test_cancel_requires_live_gate(self):
        client = FakeClient(allow_live_orders=False)
        with self.assertRaises(LiveTradingDisabledError):
            client.cancel_order("o-1")


if __name__ == "__main__":
    unittest.main()
