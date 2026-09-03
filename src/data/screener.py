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
import threading
import time
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


# Whole-market sectors, straight from NASDAQ's own `sector` field rather than a
# hand-drawn taxonomy — matching on a string the source already emits means a
# name cannot fall between two of our categories. Verified live against 7,144
# listings; counts are the observed distribution.
#
# Distinct from AI_SUPPLY_CHAIN above, which is a *thesis* (upstream bottleneck →
# downstream monetisation) and deliberately spans several of these sectors. This
# one answers "show me the whole market, organised the conventional way".
MARKET_SECTORS: Dict[str, Dict[str, Any]] = {
    "technology": {"label": "科技", "match": "Technology",
                   "role": "软件、半导体、硬件与互联网"},
    "finance": {"label": "金融", "match": "Finance",
                "role": "银行、保险、资管与交易所"},
    "health_care": {"label": "医疗健康", "match": "Health Care",
                    "role": "制药、生物科技、医疗器械与服务"},
    "consumer_discretionary": {"label": "可选消费", "match": "Consumer Discretionary",
                               "role": "零售、汽车、餐饮与娱乐"},
    "industrials": {"label": "工业", "match": "Industrials",
                    "role": "机械、航空国防、运输与建筑"},
    "energy": {"label": "能源", "match": "Energy",
               "role": "油气开采、炼化与油服"},
    "utilities": {"label": "公用事业", "match": "Utilities",
                  "role": "电力、燃气与水务，数据中心用电的承接方"},
    "real_estate": {"label": "房地产", "match": "Real Estate",
                    "role": "REITs 与地产开发"},
    "basic_materials": {"label": "基础材料", "match": "Basic Materials",
                        "role": "化工、金属与矿业"},
    "consumer_staples": {"label": "必需消费", "match": "Consumer Staples",
                         "role": "食品饮料、日用品与超市"},
    "telecom": {"label": "电信", "match": "Telecommunications",
                "role": "运营商与通信服务"},
    "miscellaneous": {"label": "其他", "match": "Miscellaneous",
                      "role": "未归入上述分类的标的"},
}


# Chinese labels for NASDAQ's 152 `industry` values. The rest of the UI is in
# Chinese, so raw English strings from the provider read as untranslated leakage
# rather than as data. Unmapped values fall through to the original string, which
# is the honest failure mode: a wrong translation is worse than an English one,
# and NASDAQ can add an industry at any time.
INDUSTRY_LABELS: Dict[str, str] = {
    "Biotechnology: Pharmaceutical Preparations": "生物科技：制剂药",
    "Blank Checks": "空白支票公司（SPAC）",
    "Major Banks": "大型银行",
    "Computer Software: Prepackaged Software": "软件：套装软件",
    "Industrial Machinery/Components": "工业机械与零部件",
    "Real Estate Investment Trusts": "房地产投资信托（REITs）",
    "Finance: Consumer Services": "金融：消费金融服务",
    "EDP Services": "数据处理服务",
    "Investment Managers": "资产管理",
    "Biotechnology: Biological Products (No Diagnostic Substances)": "生物科技：生物制品",
    "Medical/Dental Instruments": "医疗与牙科器械",
    "Oil & Gas Production": "油气开采",
    "Semiconductors": "半导体",
    "Trusts Except Educational Religious and Charitable": "信托（非教育宗教慈善类）",
    "Business Services": "商业服务",
    "Telecommunications Equipment": "通信设备",
    "Finance/Investors Services": "金融与投资者服务",
    "Computer Software: Programming Data Processing": "软件：编程与数据处理",
    "Property-Casualty Insurers": "财产与意外险",
    "Other Consumer Services": "其他消费服务",
    "Electric Utilities: Central": "电力公用事业",
    "Marine Transportation": "海运",
    "Major Chemicals": "大宗化工",
    "Precious Metals": "贵金属",
    "Investment Bankers/Brokers/Service": "投行与券商服务",
    "Real Estate": "房地产",
    "Finance Companies": "金融公司",
    "Industrial Specialties": "工业专用品",
    "Restaurants": "餐饮",
    "Services-Misc. Amusement & Recreation": "娱乐与休闲服务",
    "Professional Services": "专业服务",
    "Metal Fabrications": "金属加工",
    "Packaged Foods": "包装食品",
    "Medical Specialities": "专科医疗",
    "Metal Mining": "金属矿业",
    "Other Specialty Stores": "其他专营零售",
    "Military/Government/Technical": "军工与政府技术服务",
    "Diversified Commercial Services": "多元商业服务",
    "Auto Parts:O.E.M.": "汽车零部件（原厂配套）",
    "Beverages (Production/Distribution)": "饮料（生产与分销）",
    "Hotels/Resorts": "酒店与度假村",
    "Commercial Banks": "商业银行",
    "Savings Institutions": "储蓄机构",
    "Specialty Insurers": "专业保险",
    "Medical/Nursing Services": "医疗与护理服务",
    "Electrical Products": "电气产品",
    "Aerospace": "航空航天",
    "Homebuilding": "住宅建筑",
    "Auto Manufacturing": "汽车整车制造",
    "Farming/Seeds/Milling": "种植、种子与磨制",
    "Life Insurance": "人寿保险",
    "Catalog/Specialty Distribution": "目录与专营分销",
    "Natural Gas Distribution": "天然气分销",
    "Advertising": "广告",
    "Biotechnology: Electromedical & Electrotherapeutic Apparatus": "生物科技：电疗与电子医疗设备",
    "Apparel": "服装",
    "Steel/Iron Ore": "钢铁与铁矿",
    "Package Goods/Cosmetics": "日用品与化妆品",
    "Medicinal Chemicals and Botanical Products": "医药化学品与植物制品",
    "Power Generation": "发电",
    "Clothing/Shoe/Accessory Stores": "服装鞋帽与配饰零售",
    "Broadcasting": "广播电视",
    "Mining & Quarrying of Nonmetallic Minerals (No Fuels)": "非金属矿采选",
    "Banks": "银行",
    "Transportation Services": "运输服务",
    "Biotechnology: Laboratory Analytical Instruments": "生物科技：实验室分析仪器",
    "Consumer Electronics/Appliances": "消费电子与家电",
    "Electronic Components": "电子元器件",
    "Radio And Television Broadcasting And Communications Equipment": "广播电视与通信设备",
    "Air Freight/Delivery Services": "航空货运与快递",
    "Retail-Auto Dealers and Gas Stations": "汽车经销与加油站",
    "Trucking Freight/Courier Services": "公路货运与快递",
    "Oilfield Services/Equipment": "油服与油田设备",
    "Biotechnology: In Vitro & In Vivo Diagnostic Substances": "生物科技：体外与体内诊断试剂",
    "Engineering & Construction": "工程与建筑",
    "Computer peripheral equipment": "计算机外围设备",
    "Home Furnishings": "家居用品",
    "Recreational Games/Products/Toys": "游戏、玩具与休闲用品",
    "Cable & Other Pay Television Services": "有线与付费电视",
    "Computer Communications Equipment": "计算机通信设备",
    "Containers/Packaging": "容器与包装",
    "Integrated Freight & Logistics": "综合货运与物流",
    "Integrated oil Companies": "综合性石油公司",
    "RETAIL: Building Materials": "建材零售",
    "Construction/Ag Equipment/Trucks": "工程农机与卡车",
    "Oil and Gas Field Machinery": "油气田机械",
    "Biotechnology: Commercial Physical & Biological Resarch": "生物科技：商业化研究服务",
    "Movies/Entertainment": "影视娱乐",
    "Oil/Gas Transmission": "油气管输",
    "Department/Specialty Retail Stores": "百货与专营零售",
    "Food Chains": "食品连锁",
    "Hospital/Nursing Management": "医院与养老管理",
    "Water Supply": "供水",
    "Environmental Services": "环保服务",
    "Multi-Sector Companies": "多元化控股",
    "Other Metals and Minerals": "其他金属与矿产",
    "Coal Mining": "煤炭开采",
    "Agricultural Chemicals": "农用化学品",
    "Office Equipment/Supplies/Services": "办公设备与服务",
    "Publishing": "出版",
    "Building Products": "建筑产品",
    "Railroads": "铁路运输",
    "Computer Manufacturing": "计算机整机制造",
    "Misc Health and Biotechnology Services": "其他医疗与生物科技服务",
    "Miscellaneous manufacturing industries": "其他制造业",
    "Building Materials": "建筑材料",
    "Oil Refining/Marketing": "炼油与成品油销售",
    "Consumer Specialties": "消费专营品",
    "Other Pharmaceuticals": "其他医药",
    "Food Distributors": "食品分销",
    "Ophthalmic Goods": "眼科用品",
    "Plastic Products": "塑料制品",
    "Automotive Aftermarket": "汽车后市场",
    "Building operators": "物业运营",
    "Shoe Manufacturing": "制鞋",
    "Specialty Foods": "特色食品",
    "Fluid Controls": "流体控制",
    "Ordnance And Accessories": "武器弹药及配件",
    "Retail: Computer Software & Peripheral Equipment": "软件与外设零售",
    "Paper": "造纸",
    "Motor Vehicles": "机动车",
    "Newspapers/Magazines": "报刊杂志",
    "Water Sewer Pipeline Comm & Power Line Construction": "水务管线与电力工程",
    "Forest Products": "林产品",
    "Specialty Chemicals": "特种化工",
    "Rental/Leasing Companies": "租赁公司",
    "Auto & Home Supply Stores": "汽车与家居用品店",
    "Textiles": "纺织",
    "Meat/Poultry/Fish": "肉禽与水产",
    "Garments and Clothing": "成衣",
    "Accident &Health Insurance": "意外与健康险",
    "Diversified Financial Services": "多元金融服务",
    "Consumer Electronics/Video Chains": "消费电子连锁",
    "Medical Electronics": "医疗电子",
    "Pollution Control Equipment": "污染治理设备",
    "Retail-Drug Stores and Proprietary Stores": "药店与专卖零售",
    "Misc Corporate Leasing Services": "企业租赁服务",
    "Durable Goods": "耐用消费品",
    "Miscellaneous": "其他",
    "Books": "图书",
    "Wholesale Distributors": "批发分销",
    "Precision Instruments": "精密仪器",
    "Paints/Coatings": "涂料",
    "General Bldg Contractors - Nonresidential Bldgs": "非住宅建筑承包",
    "Aluminum": "铝业",
    "Tobacco": "烟草",
    "Professional and commerical equipment": "专业与商用设备",
    "Managed Health Care": "管理式医疗",
    "Pharmaceuticals and Biotechnology": "医药与生物科技",
    "Electronics Distribution": "电子元件分销",
    "Tools/Hardware": "工具与五金",
    "Other Transportation": "其他运输",
}


def industry_label(value: str) -> str:
    """Chinese label for an industry, or the original string when unmapped."""

    return INDUSTRY_LABELS.get(str(value or "").strip(), str(value or "").strip())


@dataclass
class ScreenedStock:
    ticker: str
    name: str
    segment: str
    segment_label: str
    industry: str
    # Chinese display label for `industry`; falls back to the raw string.
    industry_label: str
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
                industry_label=industry_label(str(row.get("industry") or "")),
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


def sector_catalogue() -> List[Dict[str, Any]]:
    """UI-facing whole-market sector list."""

    return [
        {"id": key, "label": spec["label"], "role": spec["role"], "match": spec["match"]}
        for key, spec in MARKET_SECTORS.items()
    ]


class SectorBrowser:
    """Browse the whole market by conventional sector, and search by ticker.

    Shares one fetch of NASDAQ's ~7,100-row screener with the AI-chain funnel so
    the analysis tab does not re-download the market for every interaction. The
    payload is cached in memory for `ttl_seconds` — this is a browse surface where
    a user clicks through several sectors in a row, and re-fetching 7,100 rows per
    click would be both slow and rude to the endpoint.
    """

    def __init__(self, timeout: int = 25, ttl_seconds: int = 300):
        self.screener = MarketScreener(timeout=timeout)
        self.ttl_seconds = ttl_seconds
        self._rows: Optional[List[Dict[str, Any]]] = None
        self._fetched_monotonic: float = 0.0
        self._lock = threading.Lock()

    def _listings(self) -> List[Dict[str, Any]]:
        with self._lock:
            fresh = (
                self._rows is not None
                and (time.monotonic() - self._fetched_monotonic) < self.ttl_seconds
            )
            if not fresh:
                self._rows = self.screener.fetch_listings()
                self._fetched_monotonic = time.monotonic()
            return self._rows or []

    @staticmethod
    def _row_to_stock(row: Dict[str, Any], sector_key: str, label: str) -> ScreenedStock:
        last = _to_float(row.get("lastsale"))
        volume = _to_float(row.get("volume"))
        return ScreenedStock(
            ticker=str(row.get("symbol") or "").upper().strip(),
            name=str(row.get("name") or ""),
            segment=sector_key,
            segment_label=label,
            industry=str(row.get("industry") or ""),
            industry_label=industry_label(str(row.get("industry") or "")),
            sector=str(row.get("sector") or ""),
            market_cap=_to_float(row.get("marketCap")),
            last_sale=last,
            volume=volume,
            change_pct=_to_float(row.get("pctchange")),
            dollar_volume=last * volume,
        )

    def overview(self, *, tradable: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        """Per-sector roll-up: how many names, and how the sector traded today.

        ``average_change_pct`` is dollar-volume weighted, not a plain mean. An
        unweighted average lets a $50M micro-cap move the read on a sector whose
        real behaviour is set by its megacaps.
        """

        listings = self._listings()
        buckets: Dict[str, List[ScreenedStock]] = {key: [] for key in MARKET_SECTORS}
        for row in listings:
            ticker = str(row.get("symbol") or "").upper().strip()
            if not ticker or (tradable is not None and ticker not in tradable):
                continue
            key = self._sector_key(row)
            if key is None:
                continue
            buckets[key].append(self._row_to_stock(row, key, MARKET_SECTORS[key]["label"]))

        out: List[Dict[str, Any]] = []
        for key, spec in MARKET_SECTORS.items():
            rows = buckets.get(key, [])
            weight = sum(item.dollar_volume for item in rows)
            weighted_change = (
                sum(item.change_pct * item.dollar_volume for item in rows) / weight
                if weight > 0 else 0.0
            )
            advancing = sum(1 for item in rows if item.change_pct > 0)
            out.append({
                "id": key,
                "label": spec["label"],
                "role": spec["role"],
                "count": len(rows),
                "average_change_pct": round(weighted_change, 2),
                "advancing": advancing,
                "declining": sum(1 for item in rows if item.change_pct < 0),
                # Breadth reads differently from the index move: a sector can be
                # up on two megacaps while most of its names fall.
                "breadth_pct": round(advancing / len(rows) * 100.0, 1) if rows else 0.0,
                "total_dollar_volume": round(weight, 2),
            })
        return out

    @staticmethod
    def _sector_key(row: Dict[str, Any]) -> Optional[str]:
        sector = str(row.get("sector") or "").strip().lower()
        if not sector:
            return None
        for key, spec in MARKET_SECTORS.items():
            if sector == str(spec["match"]).lower():
                return key
        return None

    def industries_in_sector(
        self,
        sector_id: str,
        *,
        tradable: Optional[Set[str]] = None,
        minimum_count: int = 3,
    ) -> List[Dict[str, Any]]:
        """Sub-industries inside one sector, with the same breadth read.

        NASDAQ tags every listing with a finer `industry` (152 distinct values)
        under the 12 coarse sectors. "Technology" alone spans prepackaged
        software, EDP services, semiconductors and semi equipment — businesses
        with almost nothing in common, so a sector-level average blurs exactly
        the distinction a user is looking for.

        Industries with fewer than ``minimum_count`` tradable names are folded
        away: a one-stock "industry" is a label, not a group, and its "breadth"
        would read 0% or 100%.
        """

        if sector_id not in MARKET_SECTORS:
            raise ValueError(f"unknown sector: {sector_id}")
        label = str(MARKET_SECTORS[sector_id]["label"])
        buckets: Dict[str, List[ScreenedStock]] = {}
        for row in self._listings():
            ticker = str(row.get("symbol") or "").upper().strip()
            if not ticker or (tradable is not None and ticker not in tradable):
                continue
            if self._sector_key(row) != sector_id:
                continue
            industry = str(row.get("industry") or "").strip()
            if not industry:
                continue
            buckets.setdefault(industry, []).append(
                self._row_to_stock(row, sector_id, label)
            )

        out: List[Dict[str, Any]] = []
        for industry, rows in buckets.items():
            if len(rows) < minimum_count:
                continue
            weight = sum(item.dollar_volume for item in rows)
            weighted_change = (
                sum(item.change_pct * item.dollar_volume for item in rows) / weight
                if weight > 0 else 0.0
            )
            advancing = sum(1 for item in rows if item.change_pct > 0)
            leader = max(rows, key=lambda item: item.dollar_volume)
            out.append({
                # `id` stays the raw NASDAQ string because it is the filter key;
                # only the display label is translated.
                "id": industry,
                "label": industry_label(industry),
                "sector": sector_id,
                "count": len(rows),
                "average_change_pct": round(weighted_change, 2),
                "breadth_pct": round(advancing / len(rows) * 100.0, 1),
                "total_dollar_volume": round(weight, 2),
                "leader": leader.ticker,
            })
        out.sort(key=lambda item: -item["total_dollar_volume"])
        return out

    def top_in_sector(
        self,
        sector_id: str,
        *,
        limit: int = 12,
        tradable: Optional[Set[str]] = None,
        minimum_dollar_volume: float = 1e7,
        order: str = "dollar_volume",
        industry: str = "",
    ) -> List[Dict[str, Any]]:
        """The most notable names in one sector, optionally one industry within it.

        ``order`` selects what "hot" means, because the honest answer depends on
        the question: ``dollar_volume`` is where the money is, ``gainers`` and
        ``losers`` are today's movers, ``market_cap`` is the sector's structure.
        """

        if sector_id not in MARKET_SECTORS:
            raise ValueError(f"unknown sector: {sector_id}")
        label = str(MARKET_SECTORS[sector_id]["label"])
        wanted_industry = industry.strip().lower()
        rows: List[ScreenedStock] = []
        for row in self._listings():
            ticker = str(row.get("symbol") or "").upper().strip()
            if not ticker or (tradable is not None and ticker not in tradable):
                continue
            if self._sector_key(row) != sector_id:
                continue
            if wanted_industry and str(row.get("industry") or "").strip().lower() != wanted_industry:
                continue
            stock = self._row_to_stock(row, sector_id, label)
            if stock.dollar_volume < minimum_dollar_volume:
                continue
            rows.append(stock)

        keys = {
            "dollar_volume": lambda item: -item.dollar_volume,
            "market_cap": lambda item: -item.market_cap,
            "gainers": lambda item: -item.change_pct,
            "losers": lambda item: item.change_pct,
        }
        rows.sort(key=keys.get(order, keys["dollar_volume"]))
        for index, item in enumerate(rows[:limit], 1):
            item.liquidity_rank = index
        return [item.to_dict() for item in rows[:limit]]

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        tradable: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Find listings by ticker or company name.

        Exact ticker matches rank first, then ticker prefixes, then name
        substrings — typing "NVDA" must not bury NVDA under companies whose
        description happens to contain the letters.
        """

        needle = str(query or "").strip().upper()
        if not needle:
            return []
        scored: List[tuple] = []
        for row in self._listings():
            ticker = str(row.get("symbol") or "").upper().strip()
            if not ticker or (tradable is not None and ticker not in tradable):
                continue
            name = str(row.get("name") or "").upper()
            if ticker == needle:
                rank = 0
            elif ticker.startswith(needle):
                rank = 1
            elif needle in ticker:
                rank = 2
            elif needle in name:
                rank = 3
            else:
                continue
            key = self._sector_key(row)
            stock = self._row_to_stock(
                row, key or "", MARKET_SECTORS[key]["label"] if key else "",
            )
            scored.append((rank, -stock.dollar_volume, stock))
        scored.sort(key=lambda item: (item[0], item[1]))
        return [item[2].to_dict() for item in scored[:limit]]
