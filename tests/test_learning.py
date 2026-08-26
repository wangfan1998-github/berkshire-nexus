from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.learning.features import FEATURE_NAMES
from src.learning.model import TrainingObservation, train_candidate
from src.learning.registry import ChampionChallengerRegistry
from src.learning.store import LearningStore


def observation(index: int, positive: bool) -> TrainingObservation:
    value = 0.9 if positive else 0.1
    features = {name: 0.5 for name in FEATURE_NAMES}
    features["analysis_score"] = value
    features["quality"] = value
    timestamp = (datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)).isoformat()
    return TrainingObservation(
        timestamp=timestamp,
        ticker=f"T{index % 5}",
        features=features,
        forward_return=0.08 if positive else -0.08,
    )


class LearningTests(unittest.TestCase):
    def test_chronological_candidate_learns_direction(self):
        values = [observation(index, positive=(index % 2 == 0)) for index in range(60)]
        run = train_candidate(values, minimum_samples=30)
        self.assertIsNotNone(run)
        assert run is not None
        self.assertGreaterEqual(run.candidate.validation_metrics.directional_accuracy, 0.90)
        self.assertGreater(
            run.candidate.model.predict_return(values[0].features),
            run.candidate.model.predict_return(values[1].features),
        )

    def test_registry_requires_explicit_or_paper_promotion(self):
        values = [observation(index, positive=(index % 2 == 0)) for index in range(60)]
        run = train_candidate(values, minimum_samples=30)
        assert run is not None
        with tempfile.TemporaryDirectory() as directory:
            registry = ChampionChallengerRegistry(Path(directory) / "registry.json")
            decision = registry.consider(run, allow_automatic_paper_promotion=False)
            self.assertFalse(decision.promoted)
            self.assertIsNone(registry.champion())
            self.assertIsNotNone(registry.challenger())

            promoted = registry.promote_challenger()
            self.assertTrue(promoted.promoted)
            self.assertEqual(registry.champion().version, run.candidate.version)

    def test_learning_store_deduplicates_imports(self):
        values = [observation(index, positive=True) for index in range(3)]
        with tempfile.TemporaryDirectory() as directory:
            store = LearningStore(Path(directory) / "learning.json")
            self.assertEqual(store.add_observations(values), 3)
            self.assertEqual(store.add_observations(values), 0)
            self.assertEqual(len(store.observations()), 3)


if __name__ == "__main__":
    unittest.main()
