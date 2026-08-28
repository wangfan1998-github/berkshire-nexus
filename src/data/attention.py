"""Social attention and news sentiment.

Two sources, both verified live and both free:

* **ApeWisdom** — ``https://apewisdom.io/api/v1.0/filter/{filter}/page/{n}``
  Reddit-derived mention counts across ~960 tickers. No key, no registration,
  but it **requires a browser User-Agent** (a bare request returns HTML, not
  JSON). Returns ``rank, ticker, name, mentions, upvotes, rank_24h_ago,
  mentions_24h_ago`` — volume only, no bull/bear score.

* **Alpha Vantage NEWS_SENTIMENT** — relevance-weighted per-ticker sentiment
  scores. Free key, 25 requests/day, so results are cached per ticker per day.

Deliberately NOT used: the X/Twitter API (no free read tier since Feb 2026,
$5/1,000 posts, Basic closed to new signups) and any X scraper (X Corp sent
cease-and-desist letters over Nitter on 2026-08-24; that repo is now archived
and its instances are down). StockTwits returns 403 to datacenter IPs.

**How this is meant to be used**: as an *attention* and *crowding* dimension,
not a directional signal. An audit of 51 finance-influencer accounts over ~18k
predictions found 45% directional accuracy — worse than chance — so social
enthusiasm is treated as a crowding warning, never as a reason to buy.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
APEWISDOM_URL = "https://apewisdom.io/api/v1.0/filter/{filter}/page/{page}"
ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
# Keyless and unquota'd. Verified live: 100 items for a single ticker versus
# Alpha Vantage's 25 requests *per day* for the whole app.
GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search"
    "?q={query}&hl=en-US&gl=US&ceid=US:en"
)

# Mention counts are heavily skewed (NVDA ~780 vs a typical name in single
# digits), so "crowded" is defined by rank and velocity rather than raw volume.
CROWDED_RANK = 10
SURGE_RATIO = 1.5


@dataclass
class BuzzEntry:
    ticker: str
    name: str = ""
    rank: int = 0
    rank_24h_ago: int = 0
    mentions: int = 0
    mentions_24h_ago: int = 0
    upvotes: int = 0

    @property
    def mention_delta(self) -> int:
        return self.mentions - self.mentions_24h_ago

    @property
    def surge_ratio(self) -> float:
        if self.mentions_24h_ago <= 0:
            return 2.0 if self.mentions > 0 else 0.0
        return self.mentions / self.mentions_24h_ago

    @property
    def is_crowded(self) -> bool:
        """Top-of-leaderboard and still accelerating."""

        return self.rank > 0 and self.rank <= CROWDED_RANK and self.surge_ratio >= SURGE_RATIO

    @property
    def is_cooling(self) -> bool:
        return self.mentions_24h_ago > 0 and self.surge_ratio < 0.6

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value.update({
            "mention_delta": self.mention_delta,
            "surge_ratio": round(self.surge_ratio, 2),
            "is_crowded": self.is_crowded,
            "is_cooling": self.is_cooling,
        })
        return value


@dataclass
class NewsSentiment:
    ticker: str
    article_count: int = 0
    # Relevance-weighted mean of per-ticker scores, in Alpha Vantage's -1..1 space.
    score: float = 0.0
    label: str = ""
    bullish_articles: int = 0
    bearish_articles: int = 0
    top_headlines: List[Dict[str, Any]] = field(default_factory=list)
    available: bool = False
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AttentionResult:
    fetched_at_utc: str = ""
    buzz: Dict[str, BuzzEntry] = field(default_factory=dict)
    sentiment: Dict[str, NewsSentiment] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    buzz_universe_size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fetched_at_utc": self.fetched_at_utc,
            "buzz": {key: value.to_dict() for key, value in self.buzz.items()},
            "sentiment": {key: value.to_dict() for key, value in self.sentiment.items()},
            "errors": self.errors,
            "buzz_universe_size": self.buzz_universe_size,
        }


def _label_for(score: float) -> str:
    """Alpha Vantage's documented bands, applied to the weighted mean."""

    if score <= -0.35:
        return "Bearish"
    if score <= -0.15:
        return "Somewhat-Bearish"
    if score < 0.15:
        return "Neutral"
    if score < 0.35:
        return "Somewhat-Bullish"
    return "Bullish"


class ApeWisdomClient:
    """Reddit mention volume. Keyless, but a browser User-Agent is required."""

    def __init__(self, timeout: int = 20, pages: int = 3, filter_name: str = "all-stocks"):
        self.timeout = timeout
        # Results are rank-ordered, so the first pages hold everything that
        # matters; fetching all 10 wastes requests on names nobody mentions.
        self.pages = max(1, int(pages))
        self.filter_name = filter_name

    def fetch(self) -> Dict[str, BuzzEntry]:
        entries: Dict[str, BuzzEntry] = {}
        for page in range(1, self.pages + 1):
            url = APEWISDOM_URL.format(filter=self.filter_name, page=page)
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
            rows = payload.get("results") or []
            if not rows:
                break
            for row in rows:
                ticker = str(row.get("ticker") or "").upper().strip()
                if not ticker:
                    continue
                entries[ticker] = BuzzEntry(
                    ticker=ticker,
                    name=str(row.get("name") or ""),
                    rank=_as_int(row.get("rank")),
                    rank_24h_ago=_as_int(row.get("rank_24h_ago")),
                    mentions=_as_int(row.get("mentions")),
                    mentions_24h_ago=_as_int(row.get("mentions_24h_ago")),
                    upvotes=_as_int(row.get("upvotes")),
                )
            if page >= _as_int(payload.get("pages"), self.pages):
                break
        return entries


class GoogleNewsClient:
    """Keyless headline feed. No quota, so it can cover every ticker every run.

    Returns headlines only — scoring is done separately, either by Alpha Vantage
    (when its quota allows) or by the configured LLM. Deliberately not FinBERT:
    that needs torch/transformers (~2GB), and this project is standard-library
    only at runtime so the desktop bundle needs no pip step.
    """

    name = "google-news-rss"

    def __init__(self, timeout: int = 20, limit: int = 25):
        self.timeout = timeout
        self.limit = max(1, int(limit))

    def fetch(self, ticker: str, company: str = "") -> List[Dict[str, str]]:
        # Including "stock" keeps a bare ticker from matching unrelated acronyms.
        query = f"{ticker} stock" if not company else f"{ticker} {company} stock"
        url = GOOGLE_NEWS_RSS.format(query=urllib.parse.quote(query))
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError:
            return []
        items: List[Dict[str, str]] = []
        for node in root.iter("item"):
            title = (node.findtext("title") or "").strip()
            if not title:
                continue
            items.append({
                "title": title[:220],
                "url": (node.findtext("link") or "").strip(),
                "published": (node.findtext("pubDate") or "").strip(),
                "source": (node.findtext("source") or "").strip(),
            })
            if len(items) >= self.limit:
                break
        return items


class AlphaVantageNewsClient:
    """Per-ticker news sentiment. Free tier allows 25 requests/day.

    Responses are cached to disk for the trading day, because the daily quota is
    smaller than a single briefing run over a 20-name shortlist.
    """

    def __init__(
        self,
        api_key: str = "",
        *,
        timeout: int = 25,
        cache_dir: Optional[Path] = None,
        daily_budget: int = 20,
    ):
        self.api_key = api_key or os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else Path(os.environ.get("TMPDIR", "/tmp"))
        self.daily_budget = max(0, int(daily_budget))
        self._spent = 0

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _cache_path(self, ticker: str) -> Path:
        day = datetime.now(timezone.utc).date().isoformat()
        return self.cache_dir / f"berkshire-nexus-news-{day}-{ticker.upper()}.json"

    def fetch(self, ticker: str) -> NewsSentiment:
        symbol = ticker.upper().strip()
        if not self.configured:
            return NewsSentiment(ticker=symbol, error="ALPHAVANTAGE_API_KEY 未配置")

        cached = self._read_cache(symbol)
        if cached is not None:
            return cached

        if self._spent >= self.daily_budget:
            return NewsSentiment(ticker=symbol, error="已达当日请求预算上限")

        params = urllib.parse.urlencode({
            "function": "NEWS_SENTIMENT",
            "tickers": symbol,
            "apikey": self.api_key,
            "limit": 50,
        })
        request = urllib.request.Request(
            f"{ALPHA_VANTAGE_URL}?{params}",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as error:
            return NewsSentiment(ticker=symbol, error=str(error)[:200])
        finally:
            self._spent += 1

        # Alpha Vantage signals quota and key problems with an Information/Note
        # field and HTTP 200, so a successful status is not enough.
        for key in ("Information", "Note", "Error Message"):
            if key in payload:
                return NewsSentiment(ticker=symbol, error=str(payload[key])[:200])

        result = self._parse(symbol, payload)
        self._write_cache(symbol, result)
        return result

    @staticmethod
    def _parse(symbol: str, payload: Dict[str, Any]) -> NewsSentiment:
        feed = payload.get("feed") or []
        weighted_sum = 0.0
        weight_total = 0.0
        bullish = 0
        bearish = 0
        headlines: List[Dict[str, Any]] = []

        for item in feed:
            if not isinstance(item, dict):
                continue
            for row in item.get("ticker_sentiment") or []:
                if str(row.get("ticker") or "").upper() != symbol:
                    continue
                relevance = _as_float(row.get("relevance_score"))
                score = _as_float(row.get("ticker_sentiment_score"))
                # Relevance-weighted: a passing mention should not move the mean
                # as much as an article about the company.
                weighted_sum += score * relevance
                weight_total += relevance
                label = str(row.get("ticker_sentiment_label") or "")
                if "Bullish" in label:
                    bullish += 1
                elif "Bearish" in label:
                    bearish += 1
                if len(headlines) < 5:
                    headlines.append({
                        "title": str(item.get("title") or "")[:200],
                        "source": str(item.get("source") or ""),
                        "url": str(item.get("url") or ""),
                        "time_published": str(item.get("time_published") or ""),
                        "relevance": round(relevance, 3),
                        "sentiment": round(score, 3),
                        "label": label,
                    })
                break

        mean = (weighted_sum / weight_total) if weight_total > 0 else 0.0
        return NewsSentiment(
            ticker=symbol,
            article_count=len(feed),
            score=round(mean, 4),
            label=_label_for(mean),
            bullish_articles=bullish,
            bearish_articles=bearish,
            top_headlines=headlines,
            available=bool(feed),
        )

    def _read_cache(self, symbol: str) -> Optional[NewsSentiment]:
        path = self._cache_path(symbol)
        try:
            if not path.exists():
                return None
            with path.open("r", encoding="utf-8") as handle:
                return NewsSentiment(**json.load(handle))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None

    def _write_cache(self, symbol: str, value: NewsSentiment) -> None:
        try:
            path = self._cache_path(symbol)
            temporary = path.with_suffix(".tmp")
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(value.to_dict(), handle, ensure_ascii=False)
            temporary.replace(path)
        except OSError:
            pass


class AttentionService:
    """Combines social buzz and news sentiment for a set of tickers."""

    _headline_errors: Dict[str, str] = {}

    def __init__(
        self,
        *,
        alpha_vantage_key: str = "",
        buzz_pages: int = 3,
        news_budget: int = 20,
        cache_dir: Optional[Path] = None,
        headline_limit: int = 8,
    ):
        self.buzz_client = ApeWisdomClient(pages=buzz_pages)
        self.news_client = AlphaVantageNewsClient(
            alpha_vantage_key, cache_dir=cache_dir, daily_budget=news_budget
        )
        # Keyless and unquota'd, so it covers every ticker on every run.
        self.headline_client = GoogleNewsClient(limit=headline_limit)

    def headlines(self, tickers: Sequence[str]) -> Dict[str, List[Dict[str, str]]]:
        """Headlines for every ticker. No quota, so nothing is left out."""

        out: Dict[str, List[Dict[str, str]]] = {}
        for ticker in tickers:
            symbol = str(ticker).upper().strip()
            if not symbol:
                continue
            try:
                out[symbol] = self.headline_client.fetch(symbol)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
                out[symbol] = []
                self._headline_errors[symbol] = str(error)[:120]
        return out

    def collect(
        self,
        tickers: Sequence[str],
        *,
        include_news: bool = True,
    ) -> AttentionResult:
        result = AttentionResult(fetched_at_utc=datetime.now(timezone.utc).isoformat())
        wanted = [str(value).upper().strip() for value in tickers if str(value).strip()]

        try:
            all_buzz = self.buzz_client.fetch()
            result.buzz_universe_size = len(all_buzz)
            # Keep only the requested names, but the ranks come from the full set
            # so "top 10 on Reddit" stays meaningful.
            result.buzz = {t: all_buzz[t] for t in wanted if t in all_buzz}
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as error:
            result.errors["apewisdom"] = str(error)[:200]

        if include_news and self.news_client.configured:
            for ticker in wanted:
                sentiment = self.news_client.fetch(ticker)
                result.sentiment[ticker] = sentiment
                if sentiment.error and "apikey" not in sentiment.error.lower():
                    result.errors.setdefault("alphavantage", sentiment.error)
        elif include_news:
            result.errors["alphavantage"] = "ALPHAVANTAGE_API_KEY 未配置"

        return result


def crowding_note(buzz: Optional[BuzzEntry]) -> str:
    """One-line crowding read, or empty when there is nothing notable.

    Phrased as a warning rather than an endorsement: high social attention is
    evidence of crowding, and the only rigorous audit of finance-influencer
    calls found sub-coin-flip directional accuracy.
    """

    if buzz is None:
        return ""
    if buzz.is_crowded:
        return (
            f"社交热度第 {buzz.rank} 位，提及量 {buzz.mentions} "
            f"（24h 前 {buzz.mentions_24h_ago}，放大 {buzz.surge_ratio:.1f}x）——"
            "关注度过热，注意接盘风险"
        )
    if buzz.is_cooling:
        return (
            f"社交热度退潮：提及量 {buzz.mentions}，较 24h 前 "
            f"{buzz.mentions_24h_ago} 下降 {(1 - buzz.surge_ratio) * 100:.0f}%"
        )
    if buzz.rank > 0:
        return f"社交热度第 {buzz.rank} 位，提及量 {buzz.mentions}（变化 {buzz.mention_delta:+d}）"
    return ""


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
