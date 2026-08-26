"""Stable, bounded feature extraction from BerkshireNexus analysis reports."""

from __future__ import annotations

import math
from typing import Dict, Tuple

from ..core.orchestrator import ComprehensiveAnalysisReport


FEATURE_NAMES: Tuple[str, ...] = (
    "analysis_score",
    "chokepoint",
    "masters_consensus",
    "margin_of_safety",
    "quality",
    "value",
    "growth",
    "momentum",
    "low_volatility",
    "revenue_growth",
    "fcf_yield",
)


def _unit(value: float, scale: float = 100.0) -> float:
    return min(max(float(value) / scale, 0.0), 1.0)


def extract_report_features(report: ComprehensiveAnalysisReport) -> Dict[str, float]:
    """Convert a report into version-stable, bounded numeric model inputs.

    Fixed-domain transforms are used instead of fitting a scaler on the entire
    dataset. This makes online inference deterministic and avoids leaking
    validation-period distribution statistics into training.
    """

    fin = report.financials
    quant = report.quant_factors
    return {
        "analysis_score": _unit(report.final_composite_score),
        "chokepoint": _unit(report.chokepoint.overall_score, 10.0),
        "masters_consensus": _unit(report.masters_debate.consensus_score, 5.0),
        "margin_of_safety": (math.tanh(report.valuation.margin_of_safety_pct / 50.0) + 1.0) / 2.0,
        "quality": _unit(quant.quality_score),
        "value": _unit(quant.value_score),
        "growth": _unit(quant.growth_score),
        "momentum": _unit(quant.momentum_score),
        "low_volatility": _unit(quant.risk_adjusted_score),
        "revenue_growth": (math.tanh(fin.revenue_growth_yoy / 0.30) + 1.0) / 2.0,
        "fcf_yield": _unit(fin.fcf_yield, 0.10),
    }
