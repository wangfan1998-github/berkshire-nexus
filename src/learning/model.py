"""Small auditable return model with chronological champion/challenger tests."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Sequence
from uuid import uuid4

from .features import FEATURE_NAMES


@dataclass(frozen=True)
class TrainingObservation:
    timestamp: str
    ticker: str
    features: Dict[str, float]
    forward_return: float

    @classmethod
    def from_dict(cls, value: Dict[str, object]) -> "TrainingObservation":
        return cls(
            timestamp=str(value["timestamp"]),
            ticker=str(value["ticker"]),
            features={str(k): float(v) for k, v in dict(value["features"]).items()},
            forward_return=float(value["forward_return"]),
        )


@dataclass(frozen=True)
class ModelMetrics:
    directional_accuracy: float
    rmse: float
    sample_count: int


@dataclass
class AdaptiveLinearModel:
    """A bounded ridge-regression model intentionally free of hidden state."""

    feature_names: Sequence[str] = field(default_factory=lambda: FEATURE_NAMES)
    weights: Dict[str, float] = field(default_factory=dict)
    intercept: float = 0.0

    def predict_return(self, features: Dict[str, float]) -> float:
        value = self.intercept
        for name in self.feature_names:
            value += self.weights.get(name, 0.0) * float(features.get(name, 0.0))
        return min(max(value, -0.50), 0.50)

    def predict_score(self, features: Dict[str, float]) -> float:
        """Map expected forward return to a familiar 0-100 conviction score."""

        return round(min(max(50.0 + self.predict_return(features) * 200.0, 0.0), 100.0), 2)

    def fit(
        self,
        observations: Sequence[TrainingObservation],
        epochs: int = 500,
        learning_rate: float = 0.08,
        l2: float = 0.01,
    ) -> "AdaptiveLinearModel":
        if not observations:
            raise ValueError("at least one training observation is required")

        self.weights = {name: 0.0 for name in self.feature_names}
        targets = [min(max(obs.forward_return, -0.50), 0.50) for obs in observations]
        self.intercept = sum(targets) / len(targets)

        for _ in range(epochs):
            weight_gradients = {name: 0.0 for name in self.feature_names}
            intercept_gradient = 0.0
            for obs, target in zip(observations, targets):
                error = self.predict_return(obs.features) - target
                intercept_gradient += error
                for name in self.feature_names:
                    weight_gradients[name] += error * float(obs.features.get(name, 0.0))

            sample_count = float(len(observations))
            self.intercept -= learning_rate * intercept_gradient / sample_count
            for name in self.feature_names:
                gradient = weight_gradients[name] / sample_count + l2 * self.weights[name]
                self.weights[name] -= learning_rate * gradient
        return self

    def to_dict(self) -> Dict[str, object]:
        return {
            "feature_names": list(self.feature_names),
            "weights": dict(self.weights),
            "intercept": self.intercept,
        }

    @classmethod
    def from_dict(cls, value: Dict[str, object]) -> "AdaptiveLinearModel":
        return cls(
            feature_names=tuple(str(v) for v in value.get("feature_names", FEATURE_NAMES)),
            weights={str(k): float(v) for k, v in dict(value.get("weights", {})).items()},
            intercept=float(value.get("intercept", 0.0)),
        )


@dataclass
class ModelArtifact:
    version: str
    trained_at_utc: str
    training_sample_count: int
    model: AdaptiveLinearModel
    validation_metrics: ModelMetrics

    def to_dict(self) -> Dict[str, object]:
        return {
            "version": self.version,
            "trained_at_utc": self.trained_at_utc,
            "training_sample_count": self.training_sample_count,
            "model": self.model.to_dict(),
            "validation_metrics": asdict(self.validation_metrics),
        }

    @classmethod
    def from_dict(cls, value: Dict[str, object]) -> "ModelArtifact":
        metrics = dict(value["validation_metrics"])
        return cls(
            version=str(value["version"]),
            trained_at_utc=str(value["trained_at_utc"]),
            training_sample_count=int(value["training_sample_count"]),
            model=AdaptiveLinearModel.from_dict(dict(value["model"])),
            validation_metrics=ModelMetrics(
                directional_accuracy=float(metrics["directional_accuracy"]),
                rmse=float(metrics["rmse"]),
                sample_count=int(metrics["sample_count"]),
            ),
        )


@dataclass(frozen=True)
class TrainingRun:
    candidate: ModelArtifact
    champion_on_current_validation: Optional[ModelMetrics]
    validation_count: int


def evaluate_model(model: AdaptiveLinearModel, observations: Sequence[TrainingObservation]) -> ModelMetrics:
    if not observations:
        return ModelMetrics(directional_accuracy=0.0, rmse=math.inf, sample_count=0)

    squared_error = 0.0
    direction_hits = 0
    for obs in observations:
        predicted = model.predict_return(obs.features)
        squared_error += (predicted - obs.forward_return) ** 2
        if (predicted >= 0.0) == (obs.forward_return >= 0.0):
            direction_hits += 1
    count = len(observations)
    return ModelMetrics(
        directional_accuracy=round(direction_hits / count, 4),
        rmse=round(math.sqrt(squared_error / count), 6),
        sample_count=count,
    )


def train_candidate(
    observations: Sequence[TrainingObservation],
    champion: Optional[AdaptiveLinearModel] = None,
    minimum_samples: int = 30,
) -> Optional[TrainingRun]:
    """Train on the past and validate strictly on the most recent observations."""

    ordered = sorted(observations, key=lambda obs: obs.timestamp)
    if len(ordered) < minimum_samples:
        return None

    split_at = max(1, int(len(ordered) * 0.80))
    split_at = min(split_at, len(ordered) - 1)
    training = ordered[:split_at]
    validation = ordered[split_at:]

    candidate_model = AdaptiveLinearModel().fit(training)
    candidate_metrics = evaluate_model(candidate_model, validation)
    champion_metrics = evaluate_model(champion, validation) if champion is not None else None
    artifact = ModelArtifact(
        version=f"model-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
        trained_at_utc=datetime.now(timezone.utc).isoformat(),
        training_sample_count=len(training),
        model=candidate_model,
        validation_metrics=candidate_metrics,
    )
    return TrainingRun(
        candidate=artifact,
        champion_on_current_validation=champion_metrics,
        validation_count=len(validation),
    )
