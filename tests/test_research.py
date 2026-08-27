from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from src.data.fetcher import DataFetcher
from src.research.ai import AIResearchService
from src.research.config import ResearchConfig
from src.research.news import NewsItem, NewsService


class _Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.value).encode("utf-8")


class MarketDataTests(unittest.TestCase):
    def test_complete_network_record_remains_non_authoritative(self):
        chart = ({
            "name": "Apple Inc.",
            "price": 200.0,
            "previous_close": 198.0,
            "price_change_pct": 1.01,
            "fifty_two_week_high": 210.0,
            "fifty_two_week_low": 150.0,
            "currency": "USD",
            "exchange": "NasdaqGS",
            "market_status": "CLOSED",
            "quote_as_of_utc": "2026-08-26T20:00:00+00:00",
            "market_data_age_seconds": 60,
        }, ([1, 2, 3], [190.0, 198.0, 200.0]))
        fundamentals = {
            "name": "Apple Inc.",
            "market_cap": 3e12,
            "revenue_growth_yoy": 0.1,
            "gross_margin": 0.45,
            "operating_margin": 0.3,
            "fcf_yield": 0.03,
            "roe": 0.8,
            "debt_to_equity": 1.1,
            "eps": 8.0,
            "_ttm_eps": 8.0,
            "_forward_eps": 9.0,
            "sector": "Technology",
            "description": "Consumer technology company.",
            "fundamentals_as_of": "2025-09-30",
        }
        fetcher = DataFetcher()
        with patch.object(fetcher, "_yahoo_chart", return_value=chart), \
                patch.object(fetcher, "_nasdaq_bundle", return_value=fundamentals), \
                patch.object(fetcher, "_calculate_beta", return_value=0.9):
            value = fetcher.fetch_quote("AAPL")

        self.assertFalse(value.uses_fallback_data)
        self.assertEqual(value.verification_level, "third-party-complete")
        self.assertFalse(value.is_authoritative)
        self.assertAlmostEqual(value.pe, 25.0)
        self.assertEqual(value.fallback_fields, [])
        self.assertEqual([item["status"] for item in value.source_trace], ["ok", "ok", "ok"])

    def test_offline_record_discloses_fallback_fields(self):
        fetcher = DataFetcher()
        with patch.object(fetcher, "_yahoo_chart", side_effect=OSError("offline")), \
                patch.object(fetcher, "_nasdaq_bundle", side_effect=OSError("offline")), \
                patch.object(fetcher, "_calculate_beta", return_value=None):
            value = fetcher.fetch_quote("TSM")

        self.assertTrue(value.uses_fallback_data)
        self.assertEqual(value.verification_level, "offline-fallback")
        self.assertIn("price", value.fallback_fields)
        self.assertTrue(any(item["status"] == "error" for item in value.source_trace))


class NewsAndAIResearchTests(unittest.TestCase):
    def test_news_has_stable_evidence_ids_and_filters_unrelated_items(self):
        service = NewsService(ResearchConfig(news_provider="yahoo", max_news_items=3))
        payload = {
            "news": [
                {"title": "Apple launches a new product", "link": "https://example.com/a", "publisher": "Wire", "providerPublishTime": 1_700_000_000, "relatedTickers": ["AAPL"]},
                {"title": "Unrelated company update", "link": "https://example.com/b", "publisher": "Wire", "providerPublishTime": 1_700_000_001, "relatedTickers": ["MSFT"]},
            ]
        }
        with patch.object(service, "_json", return_value=payload):
            result = service.fetch("AAPL", "Apple Inc.")

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].evidence_id, "N1")
        self.assertEqual(result.items[0].url, "https://example.com/a")

    def test_sec_filing_becomes_official_event_evidence(self):
        service = NewsService(ResearchConfig())
        service._sec_tickers = {"AAPL": "320193"}
        submission = {
            "name": "Apple Inc.",
            "filings": {"recent": {
                "form": ["10-Q"],
                "acceptanceDateTime": ["2026-07-31T10:01:02.000Z"],
                "filingDate": ["2026-07-31"],
                "accessionNumber": ["0000320193-26-000020"],
                "primaryDocument": ["aapl-20260627.htm"],
            }},
        }
        with patch.object(service, "_json_with_headers", return_value=submission):
            values = service._fetch_sec("AAPL", "2026-08-27T00:00:00+00:00")

        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]["publisher"], "SEC EDGAR")
        self.assertIn("10-Q", values[0]["title"])
        self.assertIn("000032019326000020", values[0]["url"])

    def test_openai_synthesis_only_accepts_supplied_citations(self):
        config = ResearchConfig(
            ai_enabled=True,
            ai_provider="openai-compatible",
            ai_model="fixture-model",
            ai_base_url="https://example.com/v1",
        )
        service = AIResearchService(config, "secret-key")
        completion = {
            "choices": [{"message": {"content": json.dumps({
                "summary": "摘要",
                "thesis": "命题",
                "catalysts": ["催化"],
                "risks": ["风险"],
                "action_bias": "BULLISH",
                "confidence": 0.8,
                "citations": ["N1", "N999"],
            }, ensure_ascii=False)}}],
            "usage": {"total_tokens": 42},
        }
        news = [NewsItem(
            evidence_id="N1",
            ticker="AAPL",
            title="Evidence",
            url="https://example.com/evidence",
            publisher="Wire",
            published_at_utc="2026-08-27T00:00:00+00:00",
            retrieved_at_utc="2026-08-27T00:01:00+00:00",
            source="fixture",
        )]
        with patch("urllib.request.urlopen", return_value=_Response(completion)):
            result = service.synthesize("AAPL", {"price": 200}, news)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.citations, ["N1"])
        self.assertEqual(result.usage["total_tokens"], 42)

    def test_missing_ai_key_is_a_degraded_result_not_analysis_exception(self):
        config = ResearchConfig(ai_enabled=True)
        result = AIResearchService(config, "").synthesize("AAPL", {}, [])
        self.assertEqual(result.status, "error")
        self.assertIn("Key", result.error or "")


if __name__ == "__main__":
    unittest.main()
