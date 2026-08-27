from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.desktop.service import DesktopService, json_safe
from src.trading.risk import RiskPolicy


class DesktopServiceTests(unittest.TestCase):
    def test_snapshot_reads_portfolio_learning_and_audit_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "paper_portfolio.json").write_text(
                json.dumps({
                    "cash": 8_000.0,
                    "quantities": {"AAPL": 10.0},
                    "prices": {"AAPL": 200.0},
                    "start_of_day_equity": 9_900.0,
                    "daily_traded_notional": 2_000.0,
                    "trading_date": "2026-08-27",
                }),
                encoding="utf-8",
            )
            (root / "learning.json").write_text(
                json.dumps({"snapshots": [{"id": 1}], "observations": [{"id": 1}]}),
                encoding="utf-8",
            )
            audit_directory = root / "audits"
            audit_directory.mkdir()
            (audit_directory / "cycle-20260827T010000Z.json").write_text(
                json.dumps({
                    "generated_at_utc": "2026-08-27T01:00:00+00:00",
                    "analyses": [{"ticker": "AAPL", "score": 80}],
                    "orders": [{"ticker": "AAPL"}],
                    "executions": [{"ticker": "AAPL"}],
                    "portfolio_after": {
                        "cash": 8_000.0,
                        "quantities": {"AAPL": 10.0},
                        "prices": {"AAPL": 200.0},
                    },
                    "champion_version": "model-test",
                }),
                encoding="utf-8",
            )

            snapshot = DesktopService(root).snapshot()

            self.assertEqual(snapshot["portfolio"]["equity"], 10_000.0)
            self.assertEqual(snapshot["portfolio"]["holdings"][0]["ticker"], "AAPL")
            self.assertEqual(snapshot["portfolio"]["holdings"][0]["weight_pct"], 20.0)
            self.assertEqual(snapshot["learning"]["snapshot_count"], 1)
            self.assertEqual(snapshot["learning"]["observation_count"], 1)
            self.assertEqual(snapshot["audits"][0]["order_count"], 1)
            self.assertNotIn("payload", snapshot["audits"][0])
            self.assertEqual(snapshot["last_cycle"]["champion_version"], "model-test")

    def test_desktop_risk_settings_can_tighten_defaults(self):
        policy = DesktopService._risk_policy({
            "minimum_analysis_score": 75,
            "max_position_pct": 5,
            "max_single_order_notional": 2_500,
            "max_daily_turnover_pct": 12,
            "max_daily_loss_pct": 0.5,
            "allowed_symbols": ["aapl", "MSFT", "AAPL"],
        })

        self.assertEqual(policy.minimum_analysis_score, 75)
        self.assertEqual(policy.max_position_pct, 5)
        self.assertEqual(policy.max_single_order_notional, 2_500)
        self.assertEqual(policy.max_daily_turnover_pct, 12)
        self.assertEqual(policy.max_daily_loss_pct, 0.5)
        self.assertEqual(policy.allowed_symbols, frozenset({"AAPL", "MSFT"}))
        self.assertFalse(policy.allow_market_orders_live)
        self.assertTrue(policy.require_verified_data_live)

    def test_desktop_risk_settings_cannot_loosen_defaults(self):
        defaults = RiskPolicy()
        invalid_values = [
            {"minimum_analysis_score": defaults.minimum_analysis_score - 1},
            {"max_position_pct": defaults.max_position_pct + 0.1},
            {"max_single_order_notional": defaults.max_single_order_notional + 1},
            {"max_daily_turnover_pct": defaults.max_daily_turnover_pct + 1},
            {"max_daily_loss_pct": defaults.max_daily_loss_pct + 0.1},
        ]
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                DesktopService._risk_policy(value)

    def test_snapshot_tolerates_corrupt_local_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "paper_portfolio.json").write_text("not json", encoding="utf-8")
            snapshot = DesktopService(root).snapshot()
            self.assertEqual(snapshot["portfolio"]["cash"], 100_000.0)
            self.assertEqual(snapshot["portfolio"]["holdings"], [])

    def test_json_safe_replaces_non_finite_numbers(self):
        self.assertEqual(
            json_safe({"infinite": float("inf"), "nested": [float("nan"), 1.0]}),
            {"infinite": None, "nested": [None, 1.0]},
        )


if __name__ == "__main__":
    unittest.main()
