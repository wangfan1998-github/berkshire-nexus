"""Current US-equity market data with explicit provenance and safe fallbacks."""

from __future__ import annotations

import json
import math
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _downsample_history(
    history: Tuple[List[int], List[float]],
    points: int = 60,
) -> List[Dict[str, Any]]:
    """Reduce a 1y daily series to ~`points` samples for a sparkline.

    Kept small on purpose: the whole briefing is serialised to JSON and handed to
    the UI, so ~250 raw points per ticker across 20 tickers would bloat it for no
    visual gain.
    """

    stamps, closes = history
    pairs = [
        (stamp, close) for stamp, close in zip(stamps, closes)
        if close is not None and close > 0
    ]
    if not pairs:
        return []
    step = max(1, len(pairs) // max(1, points))
    sampled = pairs[::step]
    # Always keep the latest point so the line ends at the current price.
    if sampled[-1] != pairs[-1]:
        sampled.append(pairs[-1])
    return [
        {"t": int(stamp), "c": round(float(close), 4)} for stamp, close in sampled
    ]


@dataclass
class CompanyFinancials:
    ticker: str
    name: str = ""
    price: float = 0.0
    pe: float = 0.0
    forward_pe: float = 0.0
    eps: float = 0.0
    beta: float = 1.0
    market_cap: float = 0.0
    revenue_growth_yoy: float = 0.0
    gross_margin: float = 0.0
    operating_margin: float = 0.0
    fcf_yield: float = 0.0
    roe: float = 0.0
    debt_to_equity: float = 0.0
    fifty_two_week_high: float = 0.0
    fifty_two_week_low: float = 0.0
    sector: str = ""
    description: str = ""
    data_source: str = "unknown"
    as_of_utc: str = ""
    uses_fallback_data: bool = True
    currency: str = "USD"
    exchange: str = ""
    market_status: str = "UNKNOWN"
    previous_close: float = 0.0
    price_change_pct: float = 0.0
    quote_as_of_utc: str = ""
    fundamentals_as_of: str = ""
    verification_level: str = "unverified"
    is_authoritative: bool = False
    market_data_age_seconds: Optional[int] = None
    fallback_fields: List[str] = field(default_factory=list)
    source_trace: List[Dict[str, Any]] = field(default_factory=list)
    # Absolute figures. A DCF must not start from price, or intrinsic value
    # scales with the quote and margin-of-safety becomes a constant.
    free_cash_flow: float = 0.0
    revenue: float = 0.0
    net_income: float = 0.0
    shareholders_equity: float = 0.0
    shares_outstanding: float = 0.0
    is_etf: bool = False
    industry: str = ""
    # Downsampled 1y daily closes for a sparkline. The series is already fetched
    # to compute beta and was being discarded; charts need it too.
    price_history: List[Dict[str, Any]] = field(default_factory=list)
    # Up to 4 fiscal years, newest first. A single trailing year cannot value a
    # cyclical: Micron's FY2025 capex ($15.9B) nearly cancelled its operating
    # cash flow ($17.5B), leaving FCF of $1.7B and a DCF that read $69 against a
    # $959 quote. Normalising across the cycle is the only way company-level
    # valuation generalises beyond steady compounders.
    operating_cash_flow_history: List[float] = field(default_factory=list)
    capex_history: List[float] = field(default_factory=list)
    depreciation_history: List[float] = field(default_factory=list)
    net_income_history: List[float] = field(default_factory=list)
    revenue_history: List[float] = field(default_factory=list)
    # Full-resolution daily OHLCV for the technical layer, oldest first (~250
    # bars). Distinct from `price_history`, which is downsampled to ~60 points for
    # the sparkline and therefore cannot support EMA129 or MACD. These are
    # stripped before the briefing is serialised — see `service._report`.
    daily_closes: List[float] = field(default_factory=list)
    daily_highs: List[float] = field(default_factory=list)
    daily_lows: List[float] = field(default_factory=list)
    daily_volumes: List[float] = field(default_factory=list)


# No per-ticker preset table. Seven symbols used to carry hand-written prices
# (TSM at $205, UBER at $79) that went stale the day they were written and were
# silently substituted whenever a provider call failed — an offline record then
# looked like a real quote from months ago. Every symbol now degrades the same
# way, through the neutral defaults below, and says so via `fallback_fields`.


class DataFetcher:
    """Route quote/history and fundamentals through independent providers.

    Yahoo Finance chart data supplies the latest available quote and one-year
    history. Nasdaq supplies annual statements, EPS history, and the company
    profile. Neither is treated as broker-authoritative execution data.
    """

    def __init__(self, timeout: int = 8):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        }
        self.nasdaq_headers = {
            **self.headers,
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/",
        }
        self._benchmark: Optional[Tuple[List[int], List[float]]] = None
        self._benchmark_lock = threading.Lock()

    def fetch_quote(self, ticker: str) -> CompanyFinancials:
        """Fetch one coherent record and disclose every substituted field."""

        sym = ticker.upper().strip()
        if not sym:
            raise ValueError("ticker is required")
        data: Dict[str, Any] = {}
        trace: List[Dict[str, Any]] = []
        fallback_fields: List[str] = []
        retrieved_at = datetime.now(timezone.utc).isoformat()
        chart_history: Tuple[List[int], List[float]] = ([], [])

        chart_started = time.monotonic()
        try:
            chart, chart_history = self._yahoo_chart(sym)
            data.update(chart)
            trace.append(self._trace(
                provider="yahoo-finance-chart",
                kind="quote+history",
                status="ok",
                started=chart_started,
                as_of=str(chart.get("quote_as_of_utc", "")),
                fields=[
                    "price", "previous_close", "fifty_two_week_high",
                    "fifty_two_week_low", "market_status",
                ],
            ))
        except Exception as error:
            trace.append(self._trace(
                provider="yahoo-finance-chart",
                kind="quote+history",
                status="error",
                started=chart_started,
                message=self._safe_error(error),
            ))

        nasdaq_started = time.monotonic()
        try:
            fundamentals = self._nasdaq_bundle(sym)
            data.update(fundamentals)
            if data.get("price") and float(data.get("_ttm_eps", 0.0)) > 0.0:
                data["pe"] = float(data["price"]) / float(data["_ttm_eps"])
            if data.get("price") and float(data.get("_forward_eps", 0.0)) > 0.0:
                data["forward_pe"] = float(data["price"]) / float(data["_forward_eps"])
            trace.append(self._trace(
                provider="nasdaq-public-api",
                kind="fundamentals+profile",
                status="ok",
                started=nasdaq_started,
                as_of=str(fundamentals.get("fundamentals_as_of", "")),
                fields=[
                    "market_cap", "eps", "forward_pe", "revenue_growth_yoy",
                    "gross_margin", "operating_margin", "fcf_yield", "roe",
                    "debt_to_equity", "sector", "description",
                ],
            ))
        except Exception as error:
            trace.append(self._trace(
                provider="nasdaq-public-api",
                kind="fundamentals+profile",
                status="error",
                started=nasdaq_started,
                message=self._safe_error(error),
            ))

        beta_started = time.monotonic()
        try:
            # Beta is conventionally a trailing-1-year measure, and the chart now
            # returns 3 years. Slice to the most recent ~252 sessions so widening
            # the window for weekly indicators does not silently redefine beta —
            # and with it every CAPM discount rate in the valuation engine.
            beta_window = (chart_history[0][-252:], chart_history[1][-252:])
            beta = self._calculate_beta(sym, beta_window)
            if beta is not None:
                data["beta"] = beta
                trace.append(self._trace(
                    provider="yahoo-finance-chart",
                    kind="derived-beta-vs-spy",
                    status="ok",
                    started=beta_started,
                    fields=["beta"],
                ))
        except Exception as error:
            trace.append(self._trace(
                provider="yahoo-finance-chart",
                kind="derived-beta-vs-spy",
                status="error",
                started=beta_started,
                message=self._safe_error(error),
            ))

        defaults: Dict[str, Any] = {
            "name": f"{sym} Inc.",
            "price": 100.0,
            "pe": 20.0,
            "forward_pe": 20.0,
            "eps": 5.0,
            "beta": 1.0,
            "market_cap": 50e9,
            "revenue_growth_yoy": 0.12,
            "gross_margin": 0.50,
            "operating_margin": 0.20,
            "fcf_yield": 0.04,
            "roe": 0.15,
            "debt_to_equity": 0.50,
            "sector": "Unknown / Unclassified",
            "description": "No verified company description was returned.",
        }
        for field_name, default in defaults.items():
            if not self._field_present(field_name, data.get(field_name)):
                data[field_name] = default
                fallback_fields.append(field_name)

        if not self._present(data.get("forward_pe")):
            data["forward_pe"] = data["pe"]
        if not self._present(data.get("fifty_two_week_high")):
            data["fifty_two_week_high"] = float(data["price"]) * 1.15
            fallback_fields.append("fifty_two_week_high")
        if not self._present(data.get("fifty_two_week_low")):
            data["fifty_two_week_low"] = float(data["price"]) * 0.85
            fallback_fields.append("fifty_two_week_low")

        fallback_fields = sorted(set(fallback_fields))
        network_quote = bool(data.get("quote_as_of_utc"))
        network_fundamentals = bool(data.get("fundamentals_as_of"))
        if network_quote and network_fundamentals and not fallback_fields:
            level = "third-party-complete"
        elif network_quote or network_fundamentals:
            level = "third-party-degraded"
        else:
            level = "offline-fallback"
        sources = []
        if network_quote:
            sources.append("yahoo-chart")
        if network_fundamentals:
            sources.append("nasdaq-fundamentals")
        if fallback_fields:
            sources.append("heuristic-fallback")

        return CompanyFinancials(
            ticker=sym,
            name=str(data["name"]),
            price=float(data["price"]),
            pe=float(data["pe"]),
            forward_pe=float(data["forward_pe"]),
            eps=float(data["eps"]),
            beta=float(data["beta"]),
            market_cap=float(data["market_cap"]),
            revenue_growth_yoy=float(data["revenue_growth_yoy"]),
            gross_margin=float(data["gross_margin"]),
            operating_margin=float(data["operating_margin"]),
            fcf_yield=float(data["fcf_yield"]),
            roe=float(data["roe"]),
            debt_to_equity=float(data["debt_to_equity"]),
            fifty_two_week_high=float(data["fifty_two_week_high"]),
            fifty_two_week_low=float(data["fifty_two_week_low"]),
            sector=str(data["sector"]),
            description=str(data["description"]),
            data_source="+".join(sources) or "offline-fallback",
            as_of_utc=str(data.get("quote_as_of_utc") or retrieved_at),
            uses_fallback_data=bool(fallback_fields),
            currency=str(data.get("currency", "USD")),
            exchange=str(data.get("exchange", "")),
            market_status=str(data.get("market_status", "UNKNOWN")),
            previous_close=float(data.get("previous_close", 0.0) or 0.0),
            price_change_pct=float(data.get("price_change_pct", 0.0) or 0.0),
            quote_as_of_utc=str(data.get("quote_as_of_utc", "")),
            fundamentals_as_of=str(data.get("fundamentals_as_of", "")),
            verification_level=level,
            # Public research feeds are never equivalent to a signed broker
            # account/order response, even when every requested field exists.
            is_authoritative=False,
            market_data_age_seconds=data.get("market_data_age_seconds"),
            fallback_fields=fallback_fields,
            free_cash_flow=float(data.get("free_cash_flow") or 0.0),
            revenue=float(data.get("revenue") or 0.0),
            net_income=float(data.get("net_income") or 0.0),
            shareholders_equity=float(data.get("shareholders_equity") or 0.0),
            industry=str(data.get("industry") or ""),
            # Sparkline stays a 1-year view: the UI labels it "一年走势" and draws
            # it against the 52-week high/low, so feeding it the full 3-year
            # series would silently mislabel the chart.
            price_history=_downsample_history(
                (chart_history[0][-252:], chart_history[1][-252:]), 60
            ),
            operating_cash_flow_history=[
                float(value) for value in (data.get("operating_cash_flow_history") or [])
            ],
            capex_history=[
                float(value) for value in (data.get("capex_history") or [])
            ],
            depreciation_history=[
                float(value) for value in (data.get("depreciation_history") or [])
            ],
            net_income_history=[
                float(value) for value in (data.get("net_income_history") or [])
            ],
            revenue_history=[
                float(value) for value in (data.get("revenue_history") or [])
            ],
            daily_closes=[float(v) for v in (data.get("daily_closes") or [])],
            daily_highs=[float(v) for v in (data.get("daily_highs") or [])],
            daily_lows=[float(v) for v in (data.get("daily_lows") or [])],
            daily_volumes=[float(v) for v in (data.get("daily_volumes") or [])],
            # An ETF has no issuer income statement: NASDAQ's fundamentals
            # endpoint returns nothing for revenue/equity/EPS. Verified live —
            # QQQM/SPYM/SMH/COWZ/URA all come back with zeros and are absent
            # from the stock screener entirely, while NVDA/CRM/TSM populate.
            is_etf=bool(
                data.get("is_etf")
                or (
                    not data.get("revenue")
                    and not data.get("shareholders_equity")
                    and not data.get("_ttm_eps")
                )
            ),
            shares_outstanding=(
                float(data["market_cap"]) / float(data["price"])
                if data.get("market_cap") and data.get("price") else 0.0
            ),
            source_trace=trace,
        )

    def _yahoo_chart(self, ticker: str) -> Tuple[Dict[str, Any], Tuple[List[int], List[float]]]:
        encoded = urllib.parse.quote(ticker, safe="")
        # 3 years, not 1. Weekly indicators need ~150 weekly bars to warm up a
        # weekly MACD and EMA60; a 1-year window folds to only ~50 weeks, which
        # cannot form them. Verified live: 1y=252 daily bars, 3y=751 (~150 weeks).
        # Beta still uses the trailing 1-year slice — see `_calculate_beta`.
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{encoded}?range=3y&interval=1d&events=div%2Csplits"
        )
        payload = self._json(url, self.headers)
        result = list(payload.get("chart", {}).get("result") or [])
        if not result:
            message = payload.get("chart", {}).get("error")
            raise ValueError(f"Yahoo chart returned no result: {message}")
        chart = dict(result[0])
        meta = dict(chart.get("meta", {}))
        timestamps = [int(value) for value in chart.get("timestamp", [])]
        quote_sets = list(chart.get("indicators", {}).get("quote", []))
        closes_raw = list(quote_sets[0].get("close", [])) if quote_sets else []
        highs_raw = list(quote_sets[0].get("high", [])) if quote_sets else []
        lows_raw = list(quote_sets[0].get("low", [])) if quote_sets else []
        volumes_raw = list(quote_sets[0].get("volume", [])) if quote_sets else []
        history = [
            (stamp, float(close))
            for stamp, close in zip(timestamps, closes_raw)
            if close is not None and math.isfinite(float(close)) and float(close) > 0.0
        ]
        # Full-resolution OHLCV for the technical layer. `history` alone is not
        # enough: it is downsampled to ~60 points for the sparkline, while EMA129
        # needs every one of the ~250 daily bars. Only bars where all four fields
        # are present are kept, so the series stay index-aligned — an indicator
        # that silently skips a bar in one series but not another is wrong in a
        # way that does not look wrong.
        bars = self._aligned_bars(closes_raw, highs_raw, lows_raw, volumes_raw)
        price = self._number(meta.get("regularMarketPrice"))
        if not price and history:
            price = history[-1][1]
        if not price:
            raise ValueError("Yahoo chart returned no current price")
        previous = history[-2][1] if len(history) >= 2 else self._number(meta.get("chartPreviousClose"))
        market_epoch = int(meta.get("regularMarketTime") or (history[-1][0] if history else 0))
        as_of = datetime.fromtimestamp(market_epoch, tz=timezone.utc).isoformat() if market_epoch else ""
        current_period = dict(meta.get("currentTradingPeriod", {}).get("regular", {}))
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        market_open = int(current_period.get("start", 0)) <= now_epoch <= int(current_period.get("end", 0))
        return ({
            "name": meta.get("longName") or meta.get("shortName"),
            "price": price,
            "previous_close": previous or 0.0,
            "price_change_pct": ((price / previous - 1.0) * 100.0) if previous else 0.0,
            "fifty_two_week_high": self._number(meta.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": self._number(meta.get("fiftyTwoWeekLow")),
            "currency": meta.get("currency") or "USD",
            "exchange": meta.get("fullExchangeName") or meta.get("exchangeName") or "",
            "market_status": "OPEN" if market_open else "CLOSED",
            "quote_as_of_utc": as_of,
            "market_data_age_seconds": max(0, now_epoch - market_epoch) if market_epoch else None,
            "daily_closes": bars["closes"],
            "daily_highs": bars["highs"],
            "daily_lows": bars["lows"],
            "daily_volumes": bars["volumes"],
        }, ([item[0] for item in history], [item[1] for item in history]))

    @staticmethod
    def _aligned_bars(
        closes: List[Any],
        highs: List[Any],
        lows: List[Any],
        volumes: List[Any],
    ) -> Dict[str, List[float]]:
        """Keep only bars where close/high/low are all present and finite.

        Yahoo returns nulls for halted sessions. Dropping a bar from one series
        but not the others would silently shift the alignment between highs and
        closes, which corrupts ATR and ADX without producing an obvious error.
        Volume is allowed to be missing and is zero-filled, since it only feeds a
        relative-volume note and never the score.
        """

        out: Dict[str, List[float]] = {"closes": [], "highs": [], "lows": [], "volumes": []}
        for index, close in enumerate(closes):
            high = highs[index] if index < len(highs) else None
            low = lows[index] if index < len(lows) else None
            if close is None or high is None or low is None:
                continue
            try:
                close_f, high_f, low_f = float(close), float(high), float(low)
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(v) for v in (close_f, high_f, low_f)):
                continue
            if close_f <= 0.0 or high_f <= 0.0 or low_f <= 0.0:
                continue
            volume = volumes[index] if index < len(volumes) else None
            try:
                volume_f = float(volume) if volume is not None else 0.0
            except (TypeError, ValueError):
                volume_f = 0.0
            out["closes"].append(close_f)
            out["highs"].append(high_f)
            out["lows"].append(low_f)
            out["volumes"].append(volume_f if math.isfinite(volume_f) else 0.0)
        return out

    def _nasdaq_bundle(self, ticker: str) -> Dict[str, Any]:
        endpoints = {
            "summary": f"https://api.nasdaq.com/api/quote/{ticker}/summary?assetclass=stocks",
            "financials": f"https://api.nasdaq.com/api/company/{ticker}/financials?frequency=1",
            "profile": f"https://api.nasdaq.com/api/company/{ticker}/company-profile",
            "eps": f"https://api.nasdaq.com/api/quote/{ticker}/eps?assetclass=stocks",
        }
        payloads: Dict[str, Dict[str, Any]] = {}
        errors: List[str] = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_map = {
                executor.submit(self._json, url, self.nasdaq_headers): name
                for name, url in endpoints.items()
            }
            for future in as_completed(future_map):
                name = future_map[future]
                try:
                    payload = future.result()
                    data = payload.get("data")
                    if not isinstance(data, dict):
                        raise ValueError("response has no data object")
                    payloads[name] = data
                except Exception as error:
                    errors.append(f"{name}: {self._safe_error(error)}")
        if "financials" not in payloads or "summary" not in payloads:
            raise ValueError("; ".join(errors) or "Nasdaq fundamentals are unavailable")

        summary = dict(payloads["summary"].get("summaryData", {}))
        financials = payloads["financials"]
        profile = payloads.get("profile", {})
        eps_payload = payloads.get("eps", {})
        income = self._statement_rows(financials.get("incomeStatementTable", {}))
        balance = self._statement_rows(financials.get("balanceSheetTable", {}))
        cashflow = self._statement_rows(financials.get("cashFlowTable", {}))
        headers = dict(financials.get("incomeStatementTable", {}).get("headers", {}))

        revenue_latest = self._statement_number(income, "Total Revenue", "value2")
        revenue_prior = self._statement_number(income, "Total Revenue", "value3")
        gross_profit = self._statement_number(income, "Gross Profit", "value2")
        operating_income = self._statement_number(income, "Operating Income", "value2")
        net_income = self._statement_number(income, "Net Income", "value2")
        equity = self._statement_number(balance, "Total Equity", "value2")
        short_debt = self._statement_number(
            balance,
            "Short-Term Debt / Current Portion of Long-Term Debt",
            "value2",
        )
        long_debt = self._statement_number(balance, "Long-Term Debt", "value2")
        operating_cash = self._statement_number(cashflow, "Net Cash Flow-Operating", "value2")
        capex = self._statement_number(cashflow, "Capital Expenditures", "value2")
        market_cap = self._number(self._summary_value(summary, "MarketCap"))

        # Full reported history (newest first). NASDAQ returns 4 fiscal years in
        # columns value2..value5; a cyclical needs all of them to be valued.
        ocf_history = self._statement_series(cashflow, "Net Cash Flow-Operating")
        capex_history = self._statement_series(cashflow, "Capital Expenditures")
        depreciation_history = self._statement_series(cashflow, "Depreciation")
        net_income_history = self._statement_series(income, "Net Income")
        revenue_history = self._statement_series(income, "Total Revenue")

        historical_eps = [
            self._number(item.get("earnings"))
            for item in eps_payload.get("earningsPerShare", [])
            if item.get("type") == "PreviousQuarter"
        ]
        forward_eps = [
            self._number(item.get("consensus"))
            for item in eps_payload.get("earningsPerShare", [])
            if item.get("type") == "UpcomingQuarter"
        ]
        ttm_eps = sum(value for value in historical_eps[-4:] if value is not None)
        next_eps = sum(value for value in forward_eps[:4] if value is not None)

        result: Dict[str, Any] = {
            "market_cap": market_cap,
            "revenue_growth_yoy": self._ratio_change(revenue_latest, revenue_prior),
            "gross_margin": self._ratio(gross_profit, revenue_latest),
            "operating_margin": self._ratio(operating_income, revenue_latest),
            "fcf_yield": self._ratio(
                (operating_cash or 0.0) + (capex or 0.0), market_cap
            ),
            # Keep the absolute value, not only the ratio.
            "free_cash_flow": (operating_cash or 0.0) + (capex or 0.0),
            "revenue": revenue_latest,
            "net_income": net_income,
            "shareholders_equity": equity,
            "operating_cash_flow_history": ocf_history,
            "capex_history": capex_history,
            "depreciation_history": depreciation_history,
            "net_income_history": net_income_history,
            "revenue_history": revenue_history,
            "roe": self._ratio(net_income, equity),
            "debt_to_equity": self._ratio(
                (short_debt or 0.0) + (long_debt or 0.0), equity
            ),
            "eps": ttm_eps or None,
            "fundamentals_as_of": str(headers.get("value2", "")),
            "name": self._profile_value(profile, "CompanyName"),
            "sector": self._profile_value(profile, "Sector")
                or self._summary_value(summary, "Sector"),
            "description": self._profile_value(profile, "CompanyDescription"),
        }
        if ttm_eps:
            # Price is merged later, so defer PE calculation with raw EPS marker.
            result["_ttm_eps"] = ttm_eps
        if next_eps:
            result["_forward_eps"] = next_eps
        return {key: value for key, value in result.items() if self._present(value)}

    def _calculate_beta(
        self,
        ticker: str,
        history: Tuple[List[int], List[float]],
    ) -> Optional[float]:
        if ticker == "SPY":
            return 1.0
        if len(history[0]) < 30:
            return None
        if self._benchmark is None:
            with self._benchmark_lock:
                if self._benchmark is None:
                    _, self._benchmark = self._yahoo_chart("SPY")
        benchmark = self._benchmark
        stock_prices = dict(zip(history[0], history[1]))
        market_prices = dict(zip(benchmark[0], benchmark[1]))
        common = sorted(set(stock_prices).intersection(market_prices))
        if len(common) < 30:
            return None
        stock_returns: List[float] = []
        market_returns: List[float] = []
        for previous, current in zip(common, common[1:]):
            stock_before, stock_after = stock_prices[previous], stock_prices[current]
            market_before, market_after = market_prices[previous], market_prices[current]
            if min(stock_before, stock_after, market_before, market_after) <= 0.0:
                continue
            stock_returns.append(stock_after / stock_before - 1.0)
            market_returns.append(market_after / market_before - 1.0)
        if len(stock_returns) < 20:
            return None
        market_mean = sum(market_returns) / len(market_returns)
        stock_mean = sum(stock_returns) / len(stock_returns)
        covariance = sum(
            (stock - stock_mean) * (market - market_mean)
            for stock, market in zip(stock_returns, market_returns)
        )
        variance = sum((value - market_mean) ** 2 for value in market_returns)
        if variance <= 1e-12:
            return None
        return round(min(max(covariance / variance, 0.05), 5.0), 4)

    def _json(self, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("provider response is not a JSON object")
        return value

    @staticmethod
    def _statement_rows(table: Any) -> Dict[str, Dict[str, Any]]:
        if not isinstance(table, dict):
            return {}
        return {
            str(row.get("value1", "")).strip(): dict(row)
            for row in table.get("rows", [])
            if isinstance(row, dict) and str(row.get("value1", "")).strip()
        }

    @classmethod
    def _statement_number(
        cls,
        rows: Dict[str, Dict[str, Any]],
        label: str,
        column: str,
    ) -> Optional[float]:
        value = cls._number(rows.get(label, {}).get(column))
        # Nasdaq financial statements are expressed in thousands of dollars.
        return value * 1000.0 if value is not None else None

    @classmethod
    def _statement_series(
        cls,
        rows: Dict[str, Dict[str, Any]],
        label: str,
    ) -> List[float]:
        """Every reported fiscal year for one line item, newest first.

        Columns value2..value5 hold the four years NASDAQ returns. Missing years
        are dropped rather than zero-filled: a zero would be read as "this
        company earned nothing that year" and drag a normalised average down.
        """

        series: List[float] = []
        for column in ("value2", "value3", "value4", "value5"):
            value = cls._statement_number(rows, label, column)
            if value is not None:
                series.append(value)
        return series

    @staticmethod
    def _summary_value(summary: Dict[str, Any], key: str) -> Any:
        value = summary.get(key, {})
        return value.get("value") if isinstance(value, dict) else value

    @staticmethod
    def _profile_value(profile: Dict[str, Any], key: str) -> Any:
        value = profile.get(key, {})
        return value.get("value") if isinstance(value, dict) else value

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        if value is None or value is False:
            return None
        if isinstance(value, (int, float)):
            result = float(value)
            return result if math.isfinite(result) else None
        normalized = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
        if not normalized or normalized in {"--", "N/A", "NA"}:
            return None
        sign = -1.0 if normalized.startswith("-") else 1.0
        normalized = normalized.lstrip("+-")
        multiplier = 1.0
        if normalized[-1:].upper() in {"K", "M", "B", "T"}:
            multiplier = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[normalized[-1].upper()]
            normalized = normalized[:-1]
        try:
            return sign * float(normalized) * multiplier
        except ValueError:
            return None

    @staticmethod
    def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
        if numerator is None or denominator is None or abs(denominator) <= 1e-12:
            return None
        return numerator / denominator

    @classmethod
    def _ratio_change(cls, current: Optional[float], previous: Optional[float]) -> Optional[float]:
        ratio = cls._ratio(current, previous)
        return ratio - 1.0 if ratio is not None else None

    @staticmethod
    def _present(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (int, float)):
            return math.isfinite(float(value))
        return True

    @classmethod
    def _field_present(cls, field_name: str, value: Any) -> bool:
        if not cls._present(value):
            return False
        if field_name in {"price", "pe", "forward_pe", "eps", "market_cap"}:
            return float(value) > 0.0
        return True

    @staticmethod
    def _trace(
        *,
        provider: str,
        kind: str,
        status: str,
        started: float,
        as_of: str = "",
        fields: Optional[Sequence[str]] = None,
        message: str = "",
    ) -> Dict[str, Any]:
        return {
            "provider": provider,
            "kind": kind,
            "status": status,
            "as_of_utc": as_of,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "latency_ms": int((time.monotonic() - started) * 1000),
            "fields": list(fields or []),
            "message": message,
        }

    @staticmethod
    def _safe_error(error: Exception) -> str:
        message = str(error).replace("\n", " ").strip()
        return message[:300] or error.__class__.__name__
