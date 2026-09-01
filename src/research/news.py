"""Current company-news retrieval with provenance, freshness, and deduplication."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .config import ResearchConfig


@dataclass(frozen=True)
class NewsItem:
    evidence_id: str
    ticker: str
    title: str
    url: str
    publisher: str
    published_at_utc: str
    retrieved_at_utc: str
    source: str
    related_tickers: List[str] = field(default_factory=list)
    content_hash: str = ""


@dataclass(frozen=True)
class NewsResult:
    status: str
    items: List[NewsItem]
    providers_attempted: List[str]
    retrieved_at_utc: str
    latency_ms: int
    error: Optional[str] = None


class NewsService:
    """Fetch recent headlines without letting missing news fail core analysis."""

    def __init__(self, config: Optional[ResearchConfig] = None, timeout: int = 8):
        self.config = config or ResearchConfig()
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Safari/537.36"
            ),
            "Accept": "application/json,application/rss+xml,text/xml,*/*",
        }
        self.sec_headers = {
            "User-Agent": "BerkshireNexus/1.3 local research app opensource@example.com",
            "Accept": "application/json",
        }
        self._sec_tickers: Optional[Dict[str, str]] = None
        self._sec_tickers_lock = threading.Lock()

    def fetch(self, ticker: str, company_name: str = "") -> NewsResult:
        started = time.monotonic()
        retrieved = datetime.now(timezone.utc).isoformat()
        if not self.config.news_enabled:
            return NewsResult(
                status="disabled",
                items=[],
                providers_attempted=[],
                retrieved_at_utc=retrieved,
                latency_ms=0,
            )

        symbol = ticker.upper().strip()
        attempted: List[str] = []
        errors: List[str] = []
        values: List[Dict[str, Any]] = []
        attempted.append("yahoo-finance-search")
        try:
            values.extend(self._fetch_yahoo(symbol, retrieved))
        except Exception as error:  # network failure is a degraded state, not analysis failure
            errors.append("Yahoo Finance: " + self._safe_error(error))

        if self.config.news_provider == "yahoo-google":
            attempted.append("sec-edgar-submissions")
            try:
                values.extend(self._fetch_sec(symbol, retrieved))
            except Exception as error:
                errors.append("SEC EDGAR: " + self._safe_error(error))
            # Google News always runs. The old condition — fewer than 3 Yahoo
            # items — never fired, because Yahoo reliably returns 5+ results;
            # verified live, `providers_attempted` never once contained
            # google-news-rss. So the feed carrying actual company events
            # ("Nvidia Just Paused Part of Its AI Financing Machine") was dead
            # code while the briefing cited portfolio-advice filler instead.
            # Both sources are keyless and unquota'd, so there is no cost to
            # merging them and letting dedup + recency sorting pick winners.
            attempted.append("google-news-rss")
            try:
                values.extend(self._fetch_google(symbol, company_name, retrieved))
            except Exception as error:
                errors.append("Google News: " + self._safe_error(error))

        deduped = self._dedupe(values)
        deduped.sort(key=lambda item: item.get("published_at_utc", ""), reverse=True)
        selected = deduped[: self.config.max_news_items]
        official = [item for item in deduped if item.get("source") == "sec-edgar-submissions"]
        if official and not any(item.get("source") == "sec-edgar-submissions" for item in selected):
            selected = (selected[:-1] + official[:1]) if selected else official[:1]
            selected.sort(key=lambda item: item.get("published_at_utc", ""), reverse=True)
        items = [
            NewsItem(evidence_id=f"N{index}", **item)
            for index, item in enumerate(selected, start=1)
        ]
        latency = int((time.monotonic() - started) * 1000)
        if items and errors:
            status = "degraded"
        elif items:
            status = "ok"
        else:
            status = "error" if errors else "empty"
        return NewsResult(
            status=status,
            items=items,
            providers_attempted=attempted,
            retrieved_at_utc=retrieved,
            latency_ms=latency,
            error="; ".join(errors) if errors else None,
        )

    def _fetch_yahoo(self, ticker: str, retrieved: str) -> List[Dict[str, Any]]:
        params = urllib.parse.urlencode({
            "q": ticker,
            "quotesCount": 1,
            "newsCount": max(self.config.max_news_items * 3, 12),
            "enableFuzzyQuery": "false",
        })
        payload = self._json(
            "https://query1.finance.yahoo.com/v1/finance/search?" + params
        )
        values: List[Dict[str, Any]] = []
        for raw in list(payload.get("news", [])):
            related = [str(value).upper() for value in raw.get("relatedTickers", [])]
            title = str(raw.get("title", "")).strip()
            url = str(raw.get("link", "")).strip()
            if not title or not url:
                continue
            if not self._is_relevant(ticker, title, related):
                continue
            published = self._epoch_iso(raw.get("providerPublishTime"))
            values.append(self._item(
                ticker=ticker,
                title=title,
                url=url,
                publisher=str(raw.get("publisher", "Yahoo Finance")).strip(),
                published=published,
                retrieved=retrieved,
                source="yahoo-finance-search",
                related=related or [ticker],
            ))
        return values

    # A story tagged with this many tickers is a roundup, not company news.
    # Verified live: Yahoo returned 10 NVDA "results" of which the top five were
    # generic listicles ("Should You Put 5% of Your Portfolio in Bitcoin?",
    # "If You'd Invested $5,000 in VOO a Decade Ago"), each tagged NVDA alongside
    # BTC-USD/VOO/^GSPC. The old filter passed anything carrying the symbol, so
    # all ten passed and the briefing's evidence pool was mostly SEO filler.
    _MAX_RELATED_TICKERS = 3
    # Phrasings that mark portfolio-advice content rather than a company event.
    _LISTICLE_MARKERS = (
        "if you'd invested", "if you had invested", "should you put",
        "here's what the numbers say", "best stocks", "top stocks",
        "stocks to buy", "millionaire", "retire", "dividend for",
        "a decade ago", "years ago", "how much $", "turn $",
    )

    @classmethod
    def _is_relevant(
        cls,
        ticker: str,
        title: str,
        related: Sequence[str],
    ) -> bool:
        """Whether a headline is about this company rather than merely tagged.

        Two independent signals, because either alone lets filler through: a
        roundup dilutes its ticker list, and an advice piece names the company in
        the title but is not reporting on it.
        """

        normalized = title.lower()
        if any(marker in normalized for marker in cls._LISTICLE_MARKERS):
            # Unless the company is genuinely the sole subject.
            if len(related) > 1:
                return False
        if len(related) > cls._MAX_RELATED_TICKERS:
            # A wide tag list is only acceptable when the title leads with the
            # symbol, which is how single-company coverage is normally written.
            return ticker in normalized.upper().split() or normalized.upper().startswith(ticker)
        if related and ticker not in [value.upper() for value in related]:
            return ticker in title.upper()
        return True

    def _fetch_sec(self, ticker: str, retrieved: str) -> List[Dict[str, Any]]:
        if self._sec_tickers is None:
            with self._sec_tickers_lock:
                if self._sec_tickers is None:
                    payload = self._json_with_headers(
                        "https://www.sec.gov/files/company_tickers.json",
                        self.sec_headers,
                    )
                    self._sec_tickers = {
                        str(item.get("ticker", "")).upper(): str(item.get("cik_str", ""))
                        for item in payload.values()
                        if isinstance(item, dict) and item.get("ticker") and item.get("cik_str")
                    }
        cik_raw = self._sec_tickers.get(ticker, "")
        if not cik_raw:
            return []
        cik = cik_raw.zfill(10)
        payload = self._json_with_headers(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            self.sec_headers,
        )
        recent = dict(payload.get("filings", {}).get("recent", {}))
        forms = list(recent.get("form", []))
        accepted = list(recent.get("acceptanceDateTime", []))
        filed = list(recent.get("filingDate", []))
        accessions = list(recent.get("accessionNumber", []))
        documents = list(recent.get("primaryDocument", []))
        descriptions = {
            "8-K": "重大事项 / 当前报告",
            "10-Q": "季度报告",
            "10-K": "年度报告",
            "6-K": "外国发行人重大事项",
            "20-F": "外国发行人年度报告",
            "40-F": "加拿大公司年度报告",
            "DEF 14A": "股东大会与代理声明",
            "SC 13D": "大股东权益变动",
            "SC 13G": "机构持股申报",
        }
        allowed = set(descriptions)
        values: List[Dict[str, Any]] = []
        company = str(payload.get("name", ticker)).strip()
        cik_path = str(int(cik_raw))
        for index, form in enumerate(forms):
            normalized_form = str(form).strip()
            if normalized_form not in allowed or len(values) >= 4:
                continue
            accession = str(accessions[index] if index < len(accessions) else "")
            document = str(documents[index] if index < len(documents) else "")
            if not accession or not document:
                continue
            accession_path = accession.replace("-", "")
            url = (
                "https://www.sec.gov/Archives/edgar/data/"
                f"{cik_path}/{accession_path}/{document}"
            )
            timestamp = str(accepted[index] if index < len(accepted) else "")
            if timestamp and not timestamp.endswith("Z") and "+" not in timestamp[10:]:
                timestamp += "+00:00"
            if not timestamp:
                day = str(filed[index] if index < len(filed) else "")
                timestamp = day + "T00:00:00+00:00" if day else ""
            values.append(self._item(
                ticker=ticker,
                title=f"{company} filed {normalized_form} — {descriptions[normalized_form]}",
                url=url,
                publisher="SEC EDGAR",
                published=timestamp,
                retrieved=retrieved,
                source="sec-edgar-submissions",
                related=[ticker],
            ))
        return values

    def _fetch_google(
        self,
        ticker: str,
        company_name: str,
        retrieved: str,
    ) -> List[Dict[str, Any]]:
        company = company_name.split(" Common Stock", 1)[0].strip()
        query = f'"{ticker}" stock'
        if company:
            query = f'("{ticker}" OR "{company}") stock when:7d'
        params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        request = urllib.request.Request(
            "https://news.google.com/rss/search?" + params,
            headers=self.headers,
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            root = ET.fromstring(response.read())
        values: List[Dict[str, Any]] = []
        for raw in root.findall("./channel/item"):
            title = (raw.findtext("title") or "").strip()
            url = (raw.findtext("link") or "").strip()
            if not title or not url:
                continue
            # Google News does not tag tickers, so relevance rests on the title.
            if not self._is_relevant(ticker, title, [ticker]):
                continue
            source = raw.find("source")
            publisher = (source.text or "Google News").strip() if source is not None else "Google News"
            published = self._rfc2822_iso(raw.findtext("pubDate"))
            values.append(self._item(
                ticker=ticker,
                title=title,
                url=url,
                publisher=publisher,
                published=published,
                retrieved=retrieved,
                source="google-news-rss",
                related=[ticker],
            ))
        return values

    def _json(self, url: str) -> Dict[str, Any]:
        return self._json_with_headers(url, self.headers)

    def _json_with_headers(self, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return dict(json.loads(response.read().decode("utf-8")))

    @staticmethod
    def _item(
        *,
        ticker: str,
        title: str,
        url: str,
        publisher: str,
        published: str,
        retrieved: str,
        source: str,
        related: Sequence[str],
    ) -> Dict[str, Any]:
        normalized = " ".join(title.lower().split())
        digest = hashlib.sha256((normalized + "|" + url).encode("utf-8")).hexdigest()
        return {
            "ticker": ticker,
            "title": title,
            "url": url,
            "publisher": publisher or source,
            "published_at_utc": published,
            "retrieved_at_utc": retrieved,
            "source": source,
            "related_tickers": list(related),
            "content_hash": digest,
        }

    @staticmethod
    def _dedupe(values: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        result: List[Dict[str, Any]] = []
        for item in values:
            title_key = " ".join(str(item.get("title", "")).lower().split())
            # Syndicated stories often differ only by publisher suffix.
            title_key = title_key.rsplit(" - ", 1)[0]
            if title_key in seen:
                continue
            seen.add(title_key)
            result.append(item)
        return result

    @staticmethod
    def _epoch_iso(value: Any) -> str:
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError, OverflowError):
            return ""

    @staticmethod
    def _rfc2822_iso(value: Optional[str]) -> str:
        try:
            parsed = parsedate_to_datetime(value or "")
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            return ""

    @staticmethod
    def _safe_error(error: Exception) -> str:
        value = str(error).replace("\n", " ").strip()
        return value[:240] or error.__class__.__name__
