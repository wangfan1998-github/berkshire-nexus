"""US-equity screening over the whole market, grouped by AI supply-chain segment.

Replaces the hardcoded four-ticker universe. The screen is a funnel:

1. NASDAQ's screener returns ~7,100 US listings in one request, each with
   sector, industry, market cap, volume and daily change. Verified live.
2. Intersect with Binance's ~7,900 tradable equity symbols (~4,700 survive), so
   nothing is analysed that cannot actually be traded here.
3. Assign each survivor to an AI supply-chain segment by industry, then rank
   within segment on liquidity and market cap.
4. Return a bounded shortlist. Full analysis costs several API calls per ticker,
   so the funnel keeps a daily run inside rate limits.

Endpoint: ``https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true``
(HTTP 200 without a key; requires a browser User-Agent).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
SCREENER_URL = (
    "https://api.nasdaq.com/api/screener/stocks"
    "?tableonly=true&limit=25&offset=0&download=true"
)

# AI supply-chain segments, ordered upstream -> downstream. Industry strings are
# matched case-insensitively against NASDAQ's `industry` field.
AI_SUPPLY_CHAIN: Dict[str, Dict[str, Any]] = {
    "semiconductors": {
        "label": "半导体 / 芯片设计与制造",
        "industries": ["semiconductors"],
        "role": "算力核心，AI 需求的直接承接方",
    },
    "semi_equipment": {
        "label": "半导体设备与材料",
        "industries": [
            "industrial machinery/components",
            "biotechnology: laboratory analytical instruments",
            "electrical products",
        ],
        "role": "产能扩张的物理瓶颈，扩产周期长",
        # Equipment makers are scattered across generic industry labels, so this
        # segment additionally requires a known-name match to stay precise.
        "require_symbol_hint": True,
        "symbol_hints": [
            "AMAT", "LRCX", "KLAC", "ASML", "TER", "ONTO", "ACLS", "UCTT",
            "AEIS", "MKSI", "COHU", "FORM", "AMKR", "ICHR", "CAMT", "NVMI",
        ],
    },
    "networking": {
        "label": "网络与互联设备",
        "industries": [
            "computer communications equipment",
            "telecommunications equipment",
            "radio and television broadcasting and communications equipment",
        ],
        "role": "集群互联，决定算力能否规模化",
    },
    "hardware_infra": {
        "label": "服务器与硬件基础设施",
        "industries": [
            "computer manufacturing",
            "computer peripheral equipment",
            "electronic components",
            "electrical products",
        ],
        "role": "整机、散热、电源与存储",
    },
    "software_platform": {
        "label": "软件与平台",
        "industries": [
            "computer software: prepackaged software",
            "computer software: programming data processing",
            "advertising",
            "retail: computer software & peripheral equipment",
        ],
        "role": "算力变现出口，模型与应用层",
    },
    "power_energy": {
        "label": "电力与能源",
        "industries": [
            "electric utilities: central",
            "power generation",
            "oil & gas production",
            "natural gas distribution",
        ],
        "role": "数据中心用电，AI 的能源约束",
    },
}


@dataclass
class ScreenedStock:
    ticker: str
    name: str
    segment: str
    segment_label: str
    industry: str
    sector: str
    market_cap: float
    last_sale: float
    volume: float
    change_pct: float
    dollar_volume: float
    liquidity_rank: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScreenResult:
    generated_at_utc: str
    total_listings: int
    tradable_listings: int
    segments: Dict[str, List[ScreenedStock]] = field(default_factory=dict)
    shortlist: List[ScreenedStock] = field(default_factory=list)
    errors: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at_utc": self.generated_at_utc,
            "total_listings": self.total_listings,
            "tradable_listings": self.tradable_listings,
            "segments": {
                key: [item.to_dict() for item in rows] for key, rows in self.segments.items()
            },
            "shortlist": [item.to_dict() for item in self.shortlist],
            "errors": self.errors,
        }

    @property
    def tickers(self) -> List[str]:
        return [item.ticker for item in self.shortlist]


def _to_float(value: Any) -> float:
    """Parse the screener's formatted numbers ("5,073,772,000,000", "$1.23", "-3.04%")."""

    if value is None:
        return 0.0
    text = str(value).strip()
    if not text or text in {"--", "N/A"}:
        return 0.0
    text = re.sub(r"[,$%\s]", "", text)
    try:
        return float(text)
    except ValueError:
        return 0.0


class MarketScreener:
    def __init__(self, timeout: int = 25):
        self.timeout = timeout

    def fetch_listings(self) -> List[Dict[str, Any]]:
        request = urllib.request.Request(
            SCREENER_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
        data = payload.get("data") or {}
        rows = data.get("rows")
        if not isinstance(rows, list):
            rows = (data.get("table") or {}).get("rows") or []
        return [row for row in rows if isinstance(row, dict) and row.get("symbol")]

    @staticmethod
    def _segment_for(row: Dict[str, Any]) -> Optional[str]:
        industry = str(row.get("industry") or "").strip().lower()
        symbol = str(row.get("symbol") or "").upper()
        if not industry:
            return None
        for key, spec in AI_SUPPLY_CHAIN.items():
            if industry not in [value.lower() for value in spec["industries"]]:
                continue
            if spec.get("require_symbol_hint"):
                # Generic industry labels alone would pull in unrelated firms.
                if symbol not in set(spec.get("symbol_hints", [])):
                    continue
            return key
        return None

    def screen(
        self,
        *,
        tradable: Optional[Set[str]] = None,
        segments: Optional[Sequence[str]] = None,
        per_segment: int = 8,
        minimum_market_cap: float = 2e9,
        minimum_dollar_volume: float = 2e7,
        include_tickers: Optional[Iterable[str]] = None,
    ) -> ScreenResult:
        """Rank AI-supply-chain names by liquidity within each segment.

        ``include_tickers`` (typically current holdings) bypass the liquidity and
        market-cap filters so an existing position is always re-evaluated and can
        be exited, never silently dropped from the analysis.
        """

        result = ScreenResult(
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            total_listings=0,
            tradable_listings=0,
        )
        try:
            listings = self.fetch_listings()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as error:
            result.errors["screener"] = str(error)
            return result

        result.total_listings = len(listings)
        wanted = set(segments) if segments else set(AI_SUPPLY_CHAIN)
        forced = {str(value).upper() for value in (include_tickers or [])}
        buckets: Dict[str, List[ScreenedStock]] = {key: [] for key in wanted}

        for row in listings:
            ticker = str(row.get("symbol") or "").upper().strip()
            if not ticker or (tradable is not None and ticker not in tradable):
                continue
            result.tradable_listings += 1
            segment = self._segment_for(row)
            if segment is None or segment not in wanted:
                continue

            market_cap = _to_float(row.get("marketCap"))
            last = _to_float(row.get("lastsale"))
            volume = _to_float(row.get("volume"))
            dollar_volume = last * volume
            is_forced = ticker in forced
            if not is_forced:
                if market_cap < minimum_market_cap:
                    continue
                if dollar_volume < minimum_dollar_volume:
                    continue

            buckets[segment].append(ScreenedStock(
                ticker=ticker,
                name=str(row.get("name") or ticker),
                segment=segment,
                segment_label=str(AI_SUPPLY_CHAIN[segment]["label"]),
                industry=str(row.get("industry") or ""),
                sector=str(row.get("sector") or ""),
                market_cap=market_cap,
                last_sale=last,
                volume=volume,
                change_pct=_to_float(row.get("pctchange")),
                dollar_volume=dollar_volume,
            ))

        shortlist: List[ScreenedStock] = []
        for key in wanted:
            rows = buckets.get(key, [])
            # Liquidity first: a thin book makes a limit order unfillable.
            rows.sort(key=lambda item: item.dollar_volume, reverse=True)
            for index, item in enumerate(rows, 1):
                item.liquidity_rank = index
            result.segments[key] = rows
            shortlist.extend(rows[: max(per_segment, 1)])

        # Any forced ticker missing from the segments still has to be analysed.
        present = {item.ticker for item in shortlist}
        for key, rows in result.segments.items():
            for item in rows:
                if item.ticker in forced and item.ticker not in present:
                    shortlist.append(item)
                    present.add(item.ticker)

        shortlist.sort(key=lambda item: (item.segment, -item.dollar_volume))
        result.shortlist = shortlist
        return result


def segment_catalogue() -> List[Dict[str, Any]]:
    """UI-facing segment list."""

    return [
        {
            "id": key,
            "label": spec["label"],
            "role": spec["role"],
            "industries": list(spec["industries"]),
        }
        for key, spec in AI_SUPPLY_CHAIN.items()
    ]
