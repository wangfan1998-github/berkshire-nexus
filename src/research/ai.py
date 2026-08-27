"""Optional, citation-constrained AI synthesis across interchangeable providers."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .config import ResearchConfig
from .news import NewsItem


PROMPT_VERSION = "research-synthesis-v1"


@dataclass(frozen=True)
class AIResearchResult:
    status: str
    provider: str
    model: str
    prompt_version: str
    generated_at_utc: str
    latency_ms: int = 0
    summary: str = ""
    thesis: str = ""
    catalysts: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    action_bias: str = "INSUFFICIENT_EVIDENCE"
    confidence: float = 0.0
    citations: List[str] = field(default_factory=list)
    usage: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class AIResearchService:
    """Synthesize supplied evidence; never retrieve data or change strategy scores."""

    def __init__(
        self,
        config: Optional[ResearchConfig] = None,
        api_key: str = "",
    ):
        self.config = config or ResearchConfig()
        self.api_key = api_key.strip()

    def synthesize(
        self,
        ticker: str,
        evidence: Dict[str, Any],
        news: Sequence[NewsItem],
    ) -> AIResearchResult:
        generated = datetime.now(timezone.utc).isoformat()
        if not self.config.ai_enabled:
            return AIResearchResult(
                status="disabled",
                provider=self.config.ai_provider,
                model=self.config.ai_model,
                prompt_version=PROMPT_VERSION,
                generated_at_utc=generated,
            )
        if self.config.ai_provider in {"openai-compatible", "gemini"} and not self.api_key:
            return self._error(
                generated,
                "AI API Key is not configured in macOS Keychain",
            )

        started = time.monotonic()
        allowed_citations = [item.evidence_id for item in news]
        prompt = self._prompt(ticker, evidence, news)
        try:
            if self.config.ai_provider in {"openai-compatible", "gemini"}:
                # Gemini exposes an OpenAI-compatible /chat/completions route.
                raw, usage = self._openai_compatible(prompt)
            elif self.config.ai_provider == "ollama":
                raw, usage = self._ollama(prompt)
            elif self.config.ai_provider == "codex-cli":
                raw, usage = self._codex_cli(prompt)
            else:  # protected by ResearchConfig validation
                raise ValueError("unsupported AI provider")
            parsed = self._parse_json(raw)
            result = self._validated_result(
                parsed,
                generated=generated,
                latency_ms=int((time.monotonic() - started) * 1000),
                allowed_citations=allowed_citations,
                usage=usage,
            )
            return result
        except Exception as error:
            return self._error(
                generated,
                self._safe_error(error),
                latency_ms=int((time.monotonic() - started) * 1000),
            )

    def test_connection(self) -> Dict[str, Any]:
        """Perform a real, minimal provider call with no market decision attached."""

        probe = {
            "company": {"ticker": "TEST", "name": "Provider connection test"},
            "deterministic_analysis": {
                "score": 50.0,
                "recommendation": "HOLD",
                "notice": "This is a connectivity probe, not investment research.",
            },
        }
        result = self.synthesize("TEST", probe, [])
        return asdict(result)

    def _openai_compatible(self, prompt: str) -> Tuple[str, Dict[str, Any]]:
        endpoint = self.config.ai_base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        payload = {
            "model": self.config.ai_model,
            "messages": [
                {
                    "role": "system",
                    "content": self._system_message(),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": self.config.ai_temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            value = self._post_openai(endpoint, payload)
        except urllib.error.HTTPError as error:
            # Several OpenAI-compatible servers implement chat/completions but
            # not response_format or temperature. Retry once with the common
            # denominator while retaining the strict JSON instruction.
            if error.code not in {400, 422}:
                raise
            compatible_payload = dict(payload)
            compatible_payload.pop("response_format", None)
            compatible_payload.pop("temperature", None)
            value = self._post_openai(endpoint, compatible_payload)
        choices = list(value.get("choices", []))
        if not choices:
            raise ValueError("AI provider returned no completion choices")
        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            content = "".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content), dict(value.get("usage", {}))

    def _post_openai(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "BerkshireNexus/1.3",
            },
            method="POST",
        )
        with urllib.request.urlopen(
            request,
            timeout=self.config.ai_timeout_seconds,
        ) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("AI provider response is not a JSON object")
        return value

    def _ollama(self, prompt: str) -> Tuple[str, Dict[str, Any]]:
        endpoint = self.config.ai_base_url.rstrip("/")
        if not endpoint.endswith("/api/chat"):
            endpoint += "/api/chat"
        payload = {
            "model": self.config.ai_model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": self._system_message()},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": self.config.ai_temperature},
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(
            request,
            timeout=self.config.ai_timeout_seconds,
        ) as response:
            value = json.loads(response.read().decode("utf-8"))
        content = value.get("message", {}).get("content", "")
        usage = {
            "prompt_tokens": value.get("prompt_eval_count"),
            "completion_tokens": value.get("eval_count"),
            "total_duration_ns": value.get("total_duration"),
        }
        return str(content), {key: val for key, val in usage.items() if val is not None}

    def _codex_cli(self, prompt: str) -> Tuple[str, Dict[str, Any]]:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "thesis": {"type": "string"},
                "catalysts": {"type": "array", "items": {"type": "string"}},
                "risks": {"type": "array", "items": {"type": "string"}},
                "action_bias": {
                    "type": "string",
                    "enum": ["BULLISH", "NEUTRAL", "BEARISH", "INSUFFICIENT_EVIDENCE"],
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "citations": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "summary", "thesis", "catalysts", "risks",
                "action_bias", "confidence", "citations",
            ],
        }
        with tempfile.TemporaryDirectory(prefix="berkshire-nexus-codex-") as directory:
            root = Path(directory)
            schema_path = root / "schema.json"
            output_path = root / "result.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = [
                "codex", "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox", "read-only",
                "--cd", str(root),
                "--model", self.config.ai_model,
                "--config", 'model_reasoning_effort="' + self.config.ai_reasoning_effort + '"',
                "--output-schema", str(schema_path),
                "--output-last-message", str(output_path),
                "-",
            ]
            completed = subprocess.run(
                command,
                input=self._system_message() + "\n\n" + prompt,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=self.config.ai_timeout_seconds,
                check=False,
                env=os.environ.copy(),
            )
            if completed.returncode != 0:
                message = completed.stderr.strip().replace("\n", " ")[:500]
                raise RuntimeError(message or "local Codex exited without a result")
            if not output_path.exists():
                raise RuntimeError("local Codex did not produce its final JSON message")
            return output_path.read_text(encoding="utf-8"), {}

    def _validated_result(
        self,
        value: Dict[str, Any],
        *,
        generated: str,
        latency_ms: int,
        allowed_citations: Iterable[str],
        usage: Dict[str, Any],
    ) -> AIResearchResult:
        allowed = set(allowed_citations)
        citations = []
        for item in value.get("citations", []):
            citation = str(item).strip().upper()
            if citation in allowed and citation not in citations:
                citations.append(citation)
        action = str(value.get("action_bias", "INSUFFICIENT_EVIDENCE")).upper()
        if action not in {"BULLISH", "NEUTRAL", "BEARISH", "INSUFFICIENT_EVIDENCE"}:
            action = "INSUFFICIENT_EVIDENCE"
        confidence = min(max(float(value.get("confidence", 0.0)), 0.0), 1.0)
        if allowed and not citations:
            # A synthesis which discusses current news without a valid evidence
            # identifier is explicitly downgraded instead of appearing sourced.
            confidence = min(confidence, 0.35)
        return AIResearchResult(
            status="ok",
            provider=self.config.ai_provider,
            model=self.config.ai_model,
            prompt_version=PROMPT_VERSION,
            generated_at_utc=generated,
            latency_ms=latency_ms,
            summary=str(value.get("summary", "")).strip()[:4000],
            thesis=str(value.get("thesis", "")).strip()[:4000],
            catalysts=self._string_list(value.get("catalysts", []), 8),
            risks=self._string_list(value.get("risks", []), 8),
            action_bias=action,
            confidence=round(confidence, 4),
            citations=citations,
            usage=usage,
        )

    def _error(
        self,
        generated: str,
        message: str,
        latency_ms: int = 0,
    ) -> AIResearchResult:
        return AIResearchResult(
            status="error",
            provider=self.config.ai_provider,
            model=self.config.ai_model,
            prompt_version=PROMPT_VERSION,
            generated_at_utc=generated,
            latency_ms=latency_ms,
            error=message,
        )

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        value = raw.strip()
        if value.startswith("```"):
            lines = value.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            value = "\n".join(lines).strip()
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("AI response must be a JSON object")
        return parsed

    @staticmethod
    def _string_list(value: Any, maximum: int) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:1000] for item in value if str(item).strip()][:maximum]

    @staticmethod
    def _system_message() -> str:
        return (
            "You are the evidence-synthesis layer of an investment research system. "
            "Use only the supplied JSON evidence. Never claim you searched the web. "
            "Never invent prices, filings, events, headlines, or citations. "
            "The deterministic score and risk rules are authoritative and must not be changed. "
            "Return only one JSON object."
        )

    @staticmethod
    def _prompt(
        ticker: str,
        evidence: Dict[str, Any],
        news: Sequence[NewsItem],
    ) -> str:
        payload = dict(evidence)
        payload["news_evidence"] = [asdict(item) for item in news]
        payload["required_output"] = {
            "summary": "Concise Chinese synthesis",
            "thesis": "One falsifiable Chinese thesis",
            "catalysts": ["Chinese string"],
            "risks": ["Chinese string"],
            "action_bias": "BULLISH | NEUTRAL | BEARISH | INSUFFICIENT_EVIDENCE",
            "confidence": "number between 0 and 1",
            "citations": ["Only evidence_id values such as N1"],
        }
        return (
            f"Synthesize the current evidence for {ticker}. Current-news statements must "
            "cite one or more supplied evidence_id values. If evidence is thin, say so.\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _safe_error(error: Exception) -> str:
        value = str(error).replace("\n", " ").strip()
        return value[:500] or error.__class__.__name__
