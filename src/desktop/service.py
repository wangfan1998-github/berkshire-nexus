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
from ..research.ai import AIResearchService
from ..research.config import ResearchConfig
from ..trading.binance_stocks import (
    LIVE_ACKNOWLEDGEMENT,
    BinanceAPIError,
    BinanceStocksClient,
    merge_quote_price,
)
from ..trading.live import LiveBroker
from ..trading.planner import AllocationPlanner
from ..trading.risk import DeterministicRiskEngine, RiskPolicy


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

    def analyze(
        self,
        tickers: Sequence[str],
        *,
        research_config: Optional[Dict[str, Any]] = None,
        ai_api_key: str = "",
    ) -> Dict[str, Any]:
        normalized = self._tickers(tickers)
        config = ResearchConfig.from_dict(research_config or {})
        reports = OmniAlphaOrchestrator(config, ai_api_key).compare_multiple(normalized)
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
        research_config: Optional[Dict[str, Any]] = None,
        ai_api_key: str = "",
    ) -> Dict[str, Any]:
        normalized = self._tickers(tickers)
        config = ResearchConfig.from_dict(research_config or {})
        reports = OmniAlphaOrchestrator(config, ai_api_key).compare_multiple(normalized)
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
    def test_ai_provider(
        research_config: Dict[str, Any],
        ai_api_key: str = "",
    ) -> Dict[str, Any]:
        config = ResearchConfig.from_dict({**research_config, "ai_enabled": True})
        return json_safe(AIResearchService(config, ai_api_key).test_connection())

    @staticmethod
    def binance_preflight(api_key: str, tickers: Sequence[str]) -> Dict[str, Any]:
        if not api_key:
            raise ValueError("Binance API Key is not configured")
        return json_safe(BinanceStocksClient(api_key=api_key).preflight(
            DesktopService._tickers(tickers)
        ))

    # ------------------------------------------------------------------
    # Live account (read-only) and live execution
    # ------------------------------------------------------------------

    @staticmethod
    def _live_client(
        api_key: str,
        api_secret: str,
        *,
        allow_live_orders: bool = False,
    ) -> BinanceStocksClient:
        if not api_key:
            raise ValueError("Binance API Key is not configured")
        if not api_secret:
            raise ValueError(
                "Binance API Secret is required to read balances or place orders"
            )
        return BinanceStocksClient(
            api_key=api_key,
            api_secret=api_secret,
            allow_live_orders=allow_live_orders,
        )

    def live_account(self, api_key: str, api_secret: str) -> Dict[str, Any]:
        """Authoritative cash, holdings and working orders straight from Binance."""

        client = self._live_client(api_key, api_secret)
        broker = LiveBroker(client, self.state_directory)
        account = broker.account_state()
        try:
            open_orders = broker.open_orders()
            open_orders_error = ""
        except (BinanceAPIError, ValueError) as error:
            open_orders = []
            open_orders_error = str(error)

        positions = list(account.get("positions", []))
        # Price the positions so the UI can show market value, not just quantity.
        prices: Dict[str, float] = {}
        quote_errors: Dict[str, str] = {}
        for position in positions:
            ticker = str(position.get("ticker", ""))
            if not ticker:
                continue
            try:
                prices[ticker] = merge_quote_price(client.latest_quote(ticker))
            except (BinanceAPIError, ValueError) as error:
                quote_errors[ticker] = str(error)
        holdings_value = 0.0
        for position in positions:
            price = float(prices.get(str(position.get("ticker", "")), 0.0))
            market_value = float(position.get("quantity", 0.0)) * price
            position["price"] = price
            position["market_value"] = market_value
            holdings_value += market_value
        cash = float(account.get("cash", 0.0))
        equity = cash + holdings_value
        for position in positions:
            position["weight_pct"] = (
                position["market_value"] / equity * 100.0 if equity > 0.0 else 0.0
            )

        return json_safe({
            "fetched_at_utc": account.get("fetched_at_utc"),
            "cash": cash,
            "cash_by_asset": account.get("cash_by_asset", {}),
            "holdings_value": holdings_value,
            "equity": equity,
            "positions": positions,
            "open_orders": open_orders,
            "open_orders_error": open_orders_error,
            "pending_local_orders": broker.has_unresolved_orders(),
            "unclassified_assets": account.get("unclassified_assets", []),
            "equity_universe_size": account.get("equity_universe_size", 0),
            "tokenized_map_size": account.get("tokenized_map_size", 0),
            "wallet_errors": account.get("wallet_errors", {}),
            "quote_errors": quote_errors,
        })

    def verify_credentials(self, api_key: str, api_secret: str) -> Dict[str, Any]:
        """Diagnose a credential pair against Binance and name the actual cause.

        Runs an unsigned call first, then a signed one, so the two failure modes
        are distinguishable: an unsigned failure means the *key* is wrong or the
        account lacks Stocks access, while an unsigned success plus a signed
        failure isolates the problem to the *secret* or its permissions.
        """

        if not api_key:
            raise ValueError("Binance API Key is not configured")
        if not api_secret:
            raise ValueError("Binance API Secret is not configured")

        checks: List[Dict[str, Any]] = []
        identical = api_key.strip() == api_secret.strip()
        checks.append({
            "name": "credentials_differ",
            "ok": not identical,
            "detail": (
                "API Key and Secret are the same value — the Secret is only shown "
                "once, at key creation time"
                if identical else "Key and Secret are different values"
            ),
        })

        client = BinanceStocksClient(api_key=api_key, api_secret=api_secret)

        # 1) Unsigned, API-key-only. Proves the key is recognised.
        unsigned_ok = False
        try:
            client.exchange_info("AAPL")
            unsigned_ok = True
            unsigned_detail = "API Key accepted for market data"
        except BinanceAPIError as error:
            unsigned_detail = f"{error.code}: {error.message}"
        except ValueError as error:
            unsigned_detail = str(error)
        checks.append({
            "name": "api_key_recognised",
            "ok": unsigned_ok,
            "detail": unsigned_detail,
        })

        # 2) Signed. Isolates secret / permission problems.
        signed_ok = False
        signed_code: Any = None
        try:
            client.funding_assets("USDC")
            signed_ok = True
            signed_detail = "Signed request accepted — credentials are usable"
        except BinanceAPIError as error:
            signed_code = error.code
            signed_detail = f"{error.code}: {error.message}"
        except ValueError as error:
            signed_detail = str(error)
        checks.append({
            "name": "signature_accepted",
            "ok": signed_ok,
            "detail": signed_detail,
        })

        # Map Binance's terse codes onto the action the operator should take.
        if signed_ok:
            diagnosis = "credentials_ok"
            guidance = "凭证可用，可以读取真实账户。"
        elif identical:
            diagnosis = "key_pasted_as_secret"
            guidance = (
                "Secret 与 API Key 相同。Binance 只在创建密钥的那一刻显示 Secret，"
                "之后无法再查看。请新建一对密钥，并在创建页面复制 Secret。"
            )
        elif signed_code == -1022:
            diagnosis = "invalid_signature"
            guidance = (
                "签名被拒。常见原因：Secret 不是这把 Key 对应的那个（比如删除重建后"
                "只更新了一边）；或创建时选了 Ed25519/RSA —— 那种密钥给的是 PEM 私钥，"
                "本版只支持 HMAC-SHA256，请改用 System generated 密钥。"
            )
        elif signed_code == -2015:
            diagnosis = "permission_or_ip"
            guidance = (
                "Key 有效但被拒绝。请检查是否勾选了 Enable Reading 权限，"
                "以及 IP 白名单是否包含你当前的出口 IP。"
            )
        elif signed_code == -1021:
            diagnosis = "clock_skew"
            guidance = "本机时间与交易所偏差过大，请开启系统自动校时后重试。"
        elif not unsigned_ok:
            diagnosis = "key_rejected"
            guidance = (
                "API Key 未被接受。请确认 Key 复制完整、未过期，"
                "且账户已开通 Binance Stocks。"
            )
        else:
            diagnosis = "signed_call_failed"
            guidance = "签名调用失败，详见下方原始错误。"

        return json_safe({
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "ok": signed_ok,
            "diagnosis": diagnosis,
            "guidance": guidance,
            "checks": checks,
        })

    def live_reconcile(self, api_key: str, api_secret: str) -> Dict[str, Any]:
        """Resolve every locally tracked order against the exchange."""

        client = self._live_client(api_key, api_secret)
        return json_safe(LiveBroker(client, self.state_directory).reconcile())

    def live_accept_disclaimer(self, api_key: str, api_secret: str) -> Dict[str, Any]:
        """Sign the US-equity disclaimer, without which every order is rejected."""

        client = self._live_client(api_key, api_secret)
        return json_safe({"response": client.accept_disclaimer()})

    def live_cancel_all(
        self,
        api_key: str,
        api_secret: str,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel working orders. Gated like any other live mutation."""

        client = self._live_client(api_key, api_secret, allow_live_orders=True)
        return json_safe(
            LiveBroker(client, self.state_directory).cancel_all_open(symbol)
        )

    def run_live_cycle(
        self,
        tickers: Sequence[str],
        *,
        api_key: str,
        api_secret: str,
        research_config: Optional[Dict[str, Any]] = None,
        ai_api_key: str = "",
        risk_config: Optional[Dict[str, Any]] = None,
        confirmation: str = "",
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Research -> plan -> risk -> (optionally) submit real orders.

        Three independent gates must all pass before any order is sent:

        1. ``confirmation`` must equal the real-money acknowledgement string.
        2. ``dry_run`` must be False.
        3. ``BinanceStocksClient`` still requires ``allow_live_orders`` plus the
           ``BERKSHIRE_NEXUS_LIVE_TRADING`` environment acknowledgement.

        ``dry_run=True`` is the default so an accidental call can only ever
        preview.
        """

        normalized = self._tickers(tickers)
        acknowledged = confirmation.strip() == LIVE_ACKNOWLEDGEMENT
        submit = acknowledged and not dry_run

        client = self._live_client(api_key, api_secret, allow_live_orders=submit)
        broker = LiveBroker(client, self.state_directory)

        # Never plan on top of unknown state: settle prior orders first.
        reconciliation = broker.reconcile()
        if submit and reconciliation.get("unresolved"):
            raise ValueError(
                "refusing to trade while previous orders are unresolved; "
                "reconcile them before enabling live submission"
            )

        config = ResearchConfig.from_dict(research_config or {})
        reports = OmniAlphaOrchestrator(config, ai_api_key).compare_multiple(normalized)

        prices: Dict[str, float] = {}
        venue_priced: List[str] = []
        for report in reports:
            ticker = report.financials.ticker
            try:
                venue_price = merge_quote_price(client.latest_quote(ticker))
            except (BinanceAPIError, ValueError):
                venue_price = 0.0
            if venue_price > 0.0:
                prices[ticker] = venue_price
                venue_priced.append(ticker)
                # The execution venue itself confirmed this price, so the record
                # is broker-authoritative for the purpose of the live risk gate.
                # Research fundamentals are still third-party; the gate exists to
                # stop stale or invented *prices* reaching the market.
                report.financials.price = venue_price
                report.financials.is_authoritative = True
                report.financials.data_source = (
                    f"binance-equity-quote+{report.financials.data_source}"
                )
            else:
                # Without a venue price the order would be priced off third-party
                # data; leave is_authoritative False so the risk engine blocks it.
                prices[ticker] = float(report.financials.price)

        portfolio = broker.live_portfolio(prices)
        policy = self._risk_policy(risk_config or {})
        planner = AllocationPlanner()
        engine = DeterministicRiskEngine(policy)

        orders = planner.plan(reports, portfolio, None)
        universe = {}
        try:
            universe = client.tradable_symbols()
        except (BinanceAPIError, ValueError):
            universe = {}

        decisions: List[Dict[str, Any]] = []
        executions: List[Dict[str, Any]] = []
        for order in orders:
            decision = engine.evaluate(order, portfolio, mode="live")
            decisions.append({
                "approved": decision.approved,
                "reasons": decision.reasons,
                "order": order.to_dict(),
                "calculated_notional": decision.calculated_notional,
                "projected_position_pct": decision.projected_position_pct,
            })
            if not submit:
                continue
            report = broker.execute(
                decision,
                portfolio,
                tradability=universe.get(order.ticker.upper()),
            )
            executions.append(report.to_dict())

        return json_safe({
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "live" if submit else "dry-run",
            "submitted": submit,
            "acknowledged": acknowledged,
            "blocked_reason": (
                "" if submit else
                "confirmation string missing" if not acknowledged else "dry_run enabled"
            ),
            "reconciliation": reconciliation,
            "portfolio": portfolio.to_dict(),
            "prices": prices,
            "venue_priced": venue_priced,
            "reports": [self._report(report) for report in reports],
            "risk_decisions": decisions,
            "executions": executions,
            "approved_count": sum(1 for item in decisions if item["approved"]),
        })

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
            "currency": report.financials.currency,
            "exchange": report.financials.exchange,
            "market_status": report.financials.market_status,
            "previous_close": report.financials.previous_close,
            "price_change_pct": report.financials.price_change_pct,
            "quote_as_of_utc": report.financials.quote_as_of_utc,
            "fundamentals_as_of": report.financials.fundamentals_as_of,
            "verification_level": report.financials.verification_level,
            "is_authoritative": report.financials.is_authoritative,
            "market_data_age_seconds": report.financials.market_data_age_seconds,
            "fallback_fields": report.financials.fallback_fields,
            "source_trace": report.financials.source_trace,
            "chokepoint": asdict(report.chokepoint),
            "masters": asdict(report.masters_debate),
            "valuation": asdict(report.valuation),
            "quant": asdict(report.quant_factors),
            "risk": asdict(report.risk_assessment),
            "news": asdict(report.news),
            "ai_research": asdict(report.ai_research),
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
