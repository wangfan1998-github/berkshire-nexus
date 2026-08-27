"""Durable analysis snapshots and delayed-return observation settlement."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union
from uuid import uuid4

from ..core.orchestrator import ComprehensiveAnalysisReport
from .features import extract_report_features
from .model import TrainingObservation


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


class LearningStore:
    """Stores raw snapshots so every training label remains reproducible."""

    def __init__(self, path: Union[Path, str]):
        self.path = Path(path)

    def _read(self) -> Dict[str, object]:
        if not self.path.exists():
            return {"snapshots": [], "observations": []}
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, value: Dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, self.path)

    def record_reports(self, reports: Iterable[ComprehensiveAnalysisReport]) -> int:
        state = self._read()
        snapshots = list(state.get("snapshots", []))
        existing_keys = {
            (str(item["ticker"]), str(item["timestamp"])[:10])
            for item in snapshots
        }
        added = 0
        for report in reports:
            key = (report.financials.ticker, report.generated_at_utc[:10])
            if key in existing_keys:
                continue
            snapshots.append({
                "id": uuid4().hex,
                "timestamp": report.generated_at_utc,
                "ticker": report.financials.ticker,
                "price": report.financials.price,
                "analysis_id": report.analysis_id,
                "data_source": report.financials.data_source,
                "uses_fallback_data": report.financials.uses_fallback_data,
                "verification_level": report.financials.verification_level,
                "is_authoritative": report.financials.is_authoritative,
                "quote_as_of_utc": report.financials.quote_as_of_utc,
                "fundamentals_as_of": report.financials.fundamentals_as_of,
                "features": extract_report_features(report),
                "settled_at": None,
            })
            existing_keys.add(key)
            added += 1
        state["snapshots"] = snapshots
        self._write(state)
        return added

    def settle_ready(
        self,
        current_prices: Dict[str, float],
        *,
        horizon_days: int = 20,
        now: Optional[datetime] = None,
    ) -> List[TrainingObservation]:
        state = self._read()
        snapshots = list(state.get("snapshots", []))
        observations = list(state.get("observations", []))
        settled: List[TrainingObservation] = []
        effective_now = now or datetime.now(timezone.utc)
        cutoff = effective_now - timedelta(days=horizon_days)

        for snapshot in snapshots:
            ticker = str(snapshot["ticker"])
            current_price = float(current_prices.get(ticker, 0.0))
            if snapshot.get("settled_at") or current_price <= 0.0:
                continue
            if _parse_timestamp(str(snapshot["timestamp"])) > cutoff:
                continue
            initial_price = float(snapshot["price"])
            if initial_price <= 0.0:
                continue
            observation = TrainingObservation(
                timestamp=str(snapshot["timestamp"]),
                ticker=ticker,
                features={str(k): float(v) for k, v in dict(snapshot["features"]).items()},
                forward_return=(current_price / initial_price) - 1.0,
            )
            observations.append({
                "snapshot_id": snapshot["id"],
                "timestamp": observation.timestamp,
                "ticker": observation.ticker,
                "features": observation.features,
                "forward_return": observation.forward_return,
                "settled_at": effective_now.isoformat(),
            })
            snapshot["settled_at"] = effective_now.isoformat()
            settled.append(observation)

        state["snapshots"] = snapshots
        state["observations"] = observations
        self._write(state)
        return settled

    def observations(self) -> List[TrainingObservation]:
        return [
            TrainingObservation.from_dict(dict(value))
            for value in self._read().get("observations", [])
        ]

    def add_observations(self, values: Iterable[TrainingObservation]) -> int:
        """Import externally labeled, point-in-time observations with dedupe."""

        state = self._read()
        observations = list(state.get("observations", []))
        existing = {
            (str(item["timestamp"]), str(item["ticker"]))
            for item in observations
        }
        added = 0
        for value in values:
            key = (value.timestamp, value.ticker)
            if key in existing:
                continue
            observations.append({
                "snapshot_id": None,
                "timestamp": value.timestamp,
                "ticker": value.ticker,
                "features": value.features,
                "forward_return": value.forward_return,
                "settled_at": datetime.now(timezone.utc).isoformat(),
            })
            existing.add(key)
            added += 1
        state["observations"] = observations
        self._write(state)
        return added
