"""Persistent champion/challenger model registry with explicit promotion gates."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Union

from .model import ModelArtifact, TrainingRun


@dataclass(frozen=True)
class PromotionDecision:
    promoted: bool
    reason: str
    champion_version: Optional[str]
    challenger_version: Optional[str]


class ChampionChallengerRegistry:
    def __init__(self, path: Union[Path, str]):
        self.path = Path(path)

    def _read(self) -> Dict[str, object]:
        if not self.path.exists():
            return {"champion": None, "challenger": None}
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, value: Dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, self.path)

    def champion(self) -> Optional[ModelArtifact]:
        raw = self._read().get("champion")
        return ModelArtifact.from_dict(dict(raw)) if raw else None

    def challenger(self) -> Optional[ModelArtifact]:
        raw = self._read().get("challenger")
        return ModelArtifact.from_dict(dict(raw)) if raw else None

    def consider(
        self,
        run: TrainingRun,
        *,
        allow_automatic_paper_promotion: bool = False,
        minimum_directional_accuracy: float = 0.55,
        minimum_accuracy_improvement: float = 0.02,
    ) -> PromotionDecision:
        state = self._read()
        state["challenger"] = run.candidate.to_dict()

        candidate_metrics = run.candidate.validation_metrics
        current_champion = state.get("champion")
        quality_passed = candidate_metrics.directional_accuracy >= minimum_directional_accuracy

        if current_champion and run.champion_on_current_validation is not None:
            previous = run.champion_on_current_validation
            quality_passed = quality_passed and (
                candidate_metrics.directional_accuracy
                >= previous.directional_accuracy + minimum_accuracy_improvement
            ) and candidate_metrics.rmse <= previous.rmse * 1.02

        promoted = bool(allow_automatic_paper_promotion and quality_passed)
        if promoted:
            state["champion"] = run.candidate.to_dict()
            state["challenger"] = None
            reason = "candidate passed chronological validation and paper-only automatic promotion gates"
        elif not allow_automatic_paper_promotion:
            reason = "candidate stored as challenger; automatic promotion is disabled"
        else:
            reason = "candidate stored as challenger; validation gates were not met"

        self._write(state)
        champion = state.get("champion")
        challenger = state.get("challenger")
        return PromotionDecision(
            promoted=promoted,
            reason=reason,
            champion_version=str(champion["version"]) if champion else None,
            challenger_version=str(challenger["version"]) if challenger else None,
        )

    def promote_challenger(self) -> PromotionDecision:
        state = self._read()
        challenger = state.get("challenger")
        if not challenger:
            return PromotionDecision(False, "no challenger is available", self._version(state.get("champion")), None)
        state["champion"] = challenger
        state["challenger"] = None
        self._write(state)
        return PromotionDecision(True, "challenger promoted by explicit operator action", str(challenger["version"]), None)

    @staticmethod
    def _version(value: object) -> Optional[str]:
        return str(value["version"]) if value else None
