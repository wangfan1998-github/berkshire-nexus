from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent.cycle import PaperTradingAgent
from src.core.orchestrator import OmniAlphaOrchestrator


class CycleTests(unittest.TestCase):
    def test_end_to_end_paper_cycle_writes_audit_and_blocks_live_quality_gap(self):
        with patch("urllib.request.urlopen", side_effect=OSError("offline fixture")):
            reports = OmniAlphaOrchestrator().compare_multiple(["TSM", "SOFI"])

        with tempfile.TemporaryDirectory() as directory:
            result = PaperTradingAgent(directory, initial_cash=20_000.0).run(reports)
            self.assertTrue(Path(result.audit_path).exists())
            self.assertGreaterEqual(result.snapshots_recorded, 2)
            self.assertTrue(all(order.tokenize is False for order in result.orders))
            with Path(result.audit_path).open("r", encoding="utf-8") as handle:
                audit = json.load(handle)
            self.assertTrue(all(value["uses_fallback_data"] for value in audit["analyses"]))
            self.assertEqual(audit["champion_version"], None)


if __name__ == "__main__":
    unittest.main()
