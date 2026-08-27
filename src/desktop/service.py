"""JSON-friendly application service used by the Tauri desktop shell."""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from ..agent.cycle import PaperTradingAgent
from ..core.orchestrator import ComprehensiveAnalysisReport, OmniAlphaOrchestrator
from ..learning.registry import ChampionChallengerRegistry
from ..trading.binance_stocks import BinanceStocksClient
from ..trading.risk import RiskPolicy


def json_safe(value: Any) -> Any:
    """Replace values which are invalid in strict JSON (notably Infinity)."""

    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe(item) for item in value]
    return value


class DesktopService:
    def __init__(self, state_directory: Union[Path, str]):
        self.state_directory = Path(state_directory).expanduser().resolve()

    def snapshot(self) -> Dict[str, Any]:
        portfolio = self._read_json(self.state_directory / "paper_portfolio.json", {})
        learning = self._read_json(
            self.state_directory / "learning.json",
            {"snapshots": [], "observations": []},
        )
        registry = self._read_json(
            self.state_directory / "model_registry.json",
            {"champion": None, "challenger": None},
        )
        audits = self._audits()
        latest_audit = audits[0]["payload"] if audits else None
        latest_portfolio = dict((latest_audit or {}).get("portfolio_after", {}))
        if latest_portfolio:
            portfolio = {**portfolio, **latest_portfolio}

        cash = float(portfolio.get("cash", 100_000.0))
        prices = {
            str(key): float(value)
            for key, value in dict(portfolio.get("prices", {})).items()
        }
        quantities = {
            str(key): float(value)
            for key, value in dict(portfolio.get("quantities", {})).items()
        }
        holdings = []
        holdings_value = 0.0
        for ticker, quantity in sorted(quantities.items()):
            price = float(prices.get(ticker, 0.0))
            market_value = quantity * price
            holdings_value += market_value
            holdings.append({
                "ticker": ticker,
                "quantity": quantity,
                "price": price,
                "market_value": market_value,
            })
        equity = cash + holdings_value
        for value in holdings:
            value["weight_pct"] = (value["market_value"] / equity * 100.0) if equity else 0.0

        risk = RiskPolicy()
        last_cycle = dict(latest_audit or {})
        return json_safe({
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "portfolio": {
                "cash": cash,
                "equity": equity,
                "holdings_value": holdings_value,
                "holdings": holdings,
                "start_of_day_equity": float(portfolio.get("start_of_day_equity", equity)),
                "daily_traded_notional": float(portfolio.get("daily_traded_notional", 0.0)),
                "trading_date": str(portfolio.get("trading_date", "")),
            },
            "learning": {
                "snapshot_count": len(list(learning.get("snapshots", []))),
                "observation_count": len(list(learning.get("observations", []))),
                "minimum_training_samples": 30,
                "champion": registry.get("champion"),
                "challenger": registry.get("challenger"),
            },
            "risk": {
                "minimum_analysis_score": risk.minimum_analysis_score,
                "max_position_pct": risk.max_position_pct,
                "max_single_order_notional": risk.max_single_order_notional,
                "max_daily_turnover_pct": risk.max_daily_turnover_pct,
                "max_daily_loss_pct": risk.max_daily_loss_pct,
                "minimum_order_notional": risk.minimum_order_notional,
                "allow_market_orders_live": risk.allow_market_orders_live,
                "require_verified_data_live": risk.require_verified_data_live,
            },
            "agent": self._read_json(
                self.state_directory / "desktop_agent_status.json",
                {"running": False, "state": "stopped", "cycles_completed": 0},
            ),
            "executions": self._executions(),
            "audits": [{key: value for key, value in item.items() if key != "payload"} for item in audits],
            "last_cycle": {
                "generated_at_utc": last_cycle.get("generated_at_utc"),
                "analyses": last_cycle.get("analyses", []),
                "orders": last_cycle.get("orders", []),
                "risk_decisions": last_cycle.get("risk_decisions", []),
                "executions": last_cycle.get("executions", []),
                "champion_version": last_cycle.get("champion_version"),
            } if last_cycle else None,
        })

    def analyze(self, tickers: Sequence[str]) -> Dict[str, Any]:
        normalized = self._tickers(tickers)
        reports = OmniAlphaOrchestrator().compare_multiple(normalized)
        return json_safe({
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "reports": [self._report(report) for report in reports],
        })

    def run_paper_cycle(
        self,
        tickers: Sequence[str],
        *,
        initial_cash: float = 100_000.0,
        auto_promote_paper: bool = False,
        risk_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized = self._tickers(tickers)
        reports = OmniAlphaOrchestrator().compare_multiple(normalized)
        result = PaperTradingAgent(
            self.state_directory,
            initial_cash=initial_cash,
            allow_automatic_paper_promotion=auto_promote_paper,
            risk_policy=self._risk_policy(risk_config or {}),
        ).run(reports)
        return json_safe({
            "cycle": result.to_dict(),
            "reports": [self._report(report) for report in reports],
            "snapshot": self.snapshot(),
        })

    def promote_model(self) -> Dict[str, Any]:
        registry = ChampionChallengerRegistry(self.state_directory / "model_registry.json")
        return json_safe(asdict(registry.promote_challenger()))

    @staticmethod
    def binance_preflight(api_key: str, tickers: Sequence[str]) -> Dict[str, Any]:
        if not api_key:
            raise ValueError("Binance API Key is not configured")
        return json_safe(BinanceStocksClient(api_key=api_key).preflight(
            DesktopService._tickers(tickers)
        ))

    @staticmethod
    def _report(report: ComprehensiveAnalysisReport) -> Dict[str, Any]:
        return {
            "analysis_id": report.analysis_id,
            "generated_at_utc": report.generated_at_utc,
            "ticker": report.financials.ticker,
            "name": report.financials.name,
            "sector": report.financials.sector,
            "price": report.financials.price,
            "pe": report.financials.pe,
            "beta": report.financials.beta,
            "score": report.final_composite_score,
            "recommendation": report.overall_recommendation,
            "data_source": report.financials.data_source,
            "uses_fallback_data": report.financials.uses_fallback_data,
            "as_of_utc": report.financials.as_of_utc,
            "chokepoint": asdict(report.chokepoint),
            "masters": asdict(report.masters_debate),
            "valuation": asdict(report.valuation),
            "quant": asdict(report.quant_factors),
            "risk": asdict(report.risk_assessment),
        }

    def _audits(self) -> List[Dict[str, Any]]:
        audit_directory = self.state_directory / "audits"
        if not audit_directory.exists():
            return []
        values: List[Dict[str, Any]] = []
        for path in sorted(audit_directory.glob("cycle-*.json"), reverse=True)[:30]:
            payload = self._read_json(path, {})
            values.append({
                "path": str(path),
                "name": path.name,
                "generated_at_utc": payload.get("generated_at_utc"),
                "order_count": len(list(payload.get("orders", []))),
                "execution_count": len(list(payload.get("executions", []))),
                "analysis_count": len(list(payload.get("analyses", []))),
                "champion_version": payload.get("champion_version"),
                "payload": payload,
            })
        return values

    def _executions(self) -> List[Dict[str, Any]]:
        path = self.state_directory / "paper_executions.jsonl"
        if not path.exists():
            return []
        values: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    try:
                        values.append(dict(json.loads(stripped)))
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
        return list(reversed(values[-40:]))

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return default

    @staticmethod
    def _tickers(values: Iterable[str]) -> List[str]:
        tickers: List[str] = []
        for value in values:
            ticker = str(value).upper().strip()
            if ticker and ticker not in tickers:
                tickers.append(ticker)
        if not tickers:
            raise ValueError("at least one US-equity ticker is required")
        return tickers

    @staticmethod
    def _risk_policy(value: Dict[str, Any]) -> RiskPolicy:
        """Build a policy while preventing the desktop UI from loosening safe defaults."""

        defaults = RiskPolicy()

        def bounded(name: str, minimum: float, safe_maximum: float, default: float) -> float:
            raw = float(value.get(name, default))
            if raw < minimum or raw > safe_maximum:
                raise ValueError(
                    f"{name} must remain between {minimum:g} and {safe_maximum:g}"
                )
            return raw

        allowlist = frozenset(DesktopService._tickers(value.get("allowed_symbols", []))) \
            if value.get("allowed_symbols") else frozenset()
        return RiskPolicy(
            minimum_analysis_score=bounded(
                "minimum_analysis_score", defaults.minimum_analysis_score, 100.0,
                defaults.minimum_analysis_score,
            ),
            max_position_pct=bounded(
                "max_position_pct", 1.0, defaults.max_position_pct,
                defaults.max_position_pct,
            ),
            max_single_order_notional=bounded(
                "max_single_order_notional", defaults.minimum_order_notional,
                defaults.max_single_order_notional, defaults.max_single_order_notional,
            ),
            max_daily_turnover_pct=bounded(
                "max_daily_turnover_pct", 1.0, defaults.max_daily_turnover_pct,
                defaults.max_daily_turnover_pct,
            ),
            max_daily_loss_pct=bounded(
                "max_daily_loss_pct", 0.1, defaults.max_daily_loss_pct,
                defaults.max_daily_loss_pct,
            ),
            minimum_order_notional=defaults.minimum_order_notional,
            allow_market_orders_live=False,
            require_verified_data_live=True,
            allowed_symbols=allowlist,
        )
