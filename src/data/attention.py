"""Social attention and news sentiment.

Two sources, both verified live and both free and keyless:

* **ApeWisdom** — ``https://apewisdom.io/api/v1.0/filter/{filter}/page/{n}``
  Reddit-derived mention counts across ~960 tickers. No key, no registration,
  but it **requires a browser User-Agent** (a bare request returns HTML, not
  JSON). Returns ``rank, ticker, name, mentions, upvotes, rank_24h_ago,
  mentions_24h_ago`` — volume only, no bull/bear score.

* **Google News RSS** — keyless, unquota'd headlines for any ticker. Scoring is
  done by the configured LLM in one batched call, which is what turns headlines
  into the -1..1 sentiment the composite score consumes.

Deliberately NOT used: **Alpha Vantage NEWS_SENTIMENT** — removed 2026-08-31.
Its free tier is 25 requests/day against a ~20-name shortlist run several times
a day, so it covered at most a handful of tickers and then failed silently for
the rest of the day. Also the X/Twitter API (no free read tier since Feb 2026,
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
# Keyless and unquota'd, which is why it replaced Alpha Vantage entirely.
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
    # Sentiment in -1..1, produced by the configured model from headlines.
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
    """Map a -1..1 sentiment score onto a coarse label.

    The bands are Alpha Vantage's, kept after that provider was removed because
    the model is prompted to emit the same vocabulary, so a model-supplied label
    and a derived one stay comparable.
    """

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


class AttentionService:
    """Combines social buzz and news sentiment for a set of tickers."""

    _headline_errors: Dict[str, str] = {}

    def __init__(
        self,
        *,
        buzz_pages: int = 3,
        cache_dir: Optional[Path] = None,
        headline_limit: int = 8,
    ):
        self.buzz_client = ApeWisdomClient(pages=buzz_pages)
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
        include_news: bool = False,
    ) -> AttentionResult:
        """Social buzz for the requested names.

        ``include_news`` is retained only for call-site compatibility and is
        ignored: sentiment now comes from Google News headlines scored by the
        configured model, which the caller drives via :meth:`headlines`.
        """

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
