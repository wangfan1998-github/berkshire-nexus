"""Validated runtime configuration for data, news, and AI research providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict
from urllib.parse import urlparse


# "openai-compatible" covers every vendor exposing /chat/completions, which is
# how Gemini, DeepSeek, Kimi, Doubao, OpenRouter and vLLM are all reached.
_AI_PROVIDERS = frozenset({"openai-compatible", "gemini", "ollama", "codex-cli"})

# Convenience presets so the UI can fill base_url/model without the user
# hunting for them. Gemini's endpoint verified live: an invalid key returns
# HTTP 400 "Please pass a valid API key", so the route exists.
AI_PRESETS = {
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
        "default_model": "gemini-2.5-flash",
    },
    "openai-compatible": {
        "label": "OpenAI 兼容 (OpenAI / DeepSeek / Kimi / \u8c46\u5305 / OpenRouter)",
        "base_url": "https://api.openai.com/v1",
        "models": [],
        "default_model": "gpt-4o-mini",
    },
    "ollama": {
        "label": "Ollama (\u672c\u5730)",
        "base_url": "http://localhost:11434",
        "models": ["llama3.1", "qwen2.5"],
        "default_model": "llama3.1",
    },
    "codex-cli": {
        "label": "Codex CLI (\u672c\u673a\uff0c\u65e0\u9700 Key)",
        "base_url": "",
        "models": [],
        "default_model": "gpt-5.1-codex",
    },
}
_NEWS_PROVIDERS = frozenset({"yahoo", "yahoo-google"})


@dataclass(frozen=True)
class ResearchConfig:
    """Non-secret provider settings.

    Credentials are deliberately not part of this object. The desktop bridge
    supplies them through an environment variable read from macOS Keychain.
    """

    market_provider: str = "yahoo-nasdaq"
    news_enabled: bool = True
    news_provider: str = "yahoo-google"
    max_news_items: int = 6
    ai_enabled: bool = False
    ai_provider: str = "openai-compatible"
    ai_model: str = "gpt-5-mini"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_timeout_seconds: int = 90
    ai_temperature: float = 0.2
    ai_reasoning_effort: str = "medium"

    @classmethod
    def from_dict(cls, value: Any) -> "ResearchConfig":
        raw: Dict[str, Any] = dict(value or {}) if isinstance(value, dict) else {}
        config = cls(
            market_provider=str(raw.get("market_provider", cls.market_provider)).strip(),
            news_enabled=bool(raw.get("news_enabled", cls.news_enabled)),
            news_provider=str(raw.get("news_provider", cls.news_provider)).strip(),
            max_news_items=int(raw.get("max_news_items", cls.max_news_items)),
            ai_enabled=bool(raw.get("ai_enabled", cls.ai_enabled)),
            ai_provider=str(raw.get("ai_provider", cls.ai_provider)).strip(),
            ai_model=str(raw.get("ai_model", cls.ai_model)).strip(),
            ai_base_url=str(raw.get("ai_base_url", cls.ai_base_url)).strip(),
            ai_timeout_seconds=int(raw.get("ai_timeout_seconds", cls.ai_timeout_seconds)),
            ai_temperature=float(raw.get("ai_temperature", cls.ai_temperature)),
            ai_reasoning_effort=str(
                raw.get("ai_reasoning_effort", cls.ai_reasoning_effort)
            ).strip(),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.market_provider != "yahoo-nasdaq":
            raise ValueError("market_provider currently supports only yahoo-nasdaq")
        if self.news_provider not in _NEWS_PROVIDERS:
            raise ValueError("news_provider must be yahoo or yahoo-google")
        if not 1 <= self.max_news_items <= 12:
            raise ValueError("max_news_items must remain between 1 and 12")
        if self.ai_provider not in _AI_PROVIDERS:
            raise ValueError(
                "ai_provider must be openai-compatible, ollama, or codex-cli"
            )
        if self.ai_enabled and not self.ai_model:
            raise ValueError("ai_model is required when AI research is enabled")
        if not 10 <= self.ai_timeout_seconds <= 300:
            raise ValueError("ai_timeout_seconds must remain between 10 and 300")
        if not 0.0 <= self.ai_temperature <= 1.0:
            raise ValueError("ai_temperature must remain between 0 and 1")
        if self.ai_provider not in {"codex-cli"}:
            parsed = urlparse(self.ai_base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("ai_base_url must be an absolute HTTP(S) URL")
        if self.ai_reasoning_effort not in {
            "none", "minimal", "low", "medium", "high", "xhigh"
        }:
            raise ValueError("unsupported ai_reasoning_effort")
