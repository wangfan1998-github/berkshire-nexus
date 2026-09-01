"""Entry gates shared by the briefing and the order planner.

One decision model, imported by both surfaces. Keeping these rules in the
briefing alone let the two drift: the briefing would show AVOID on a name that
had already run +8% today, while the planner — which re-runs its own analysis —
still sized a buy for it. A user who followed a briefing marked 建仓/加仓 could
land on an execution preview that disagreed with it.

A gate blocks *adding to* a position. It never blocks trimming or exiting: those
are risk-reducing and must always remain available.
"""

from __future__ import annotations

from typing import Optional

from .orchestrator import ComprehensiveAnalysisReport


# A single-day move beyond this is chasing, not accumulating. Applied as a hard
# gate rather than a score adjustment: momentum carries only a few percent of the
# composite, so a +22% day could shift the score by ~1.5 points and never block
# an entry.
CHASE_DAY_PCT = 5.0
# Near the top of the 52-week range most of the move is already priced in.
CHASE_RANGE_PCT = 92.0
# ETFs hold dozens to hundreds of names, so the single-name concentration limit
# does not apply; capping an index fund at 6% would shred a diversified holding.
ETF_POSITION_CAP_PCT = 30.0

# Entry may be granted on relative standing when the absolute line is not met.
# A name must sit in the top quartile of the day's analysed universe.
TOP_QUANTILE_PCT = 75.0
# Ranking is meaningless on a handful of names — "top quartile of 3" is one
# ticker chosen by rounding. Below this, only the absolute test applies.
MIN_RANKED_UNIVERSE = 8

# Valuation gate. The percentile floor is the working constraint; the absolute
# floor only catches cases where the DCF itself has clearly broken down (a
# -300% margin means the cash-flow base is wrong, not that the stock is 4x rich).
VALUATION_MIN_PERCENTILE = 25.0
VALUATION_FLOOR_PCT = -150.0


def qualifies_on_rank(
    report: ComprehensiveAnalysisReport,
    entry_percentile: float = TOP_QUANTILE_PCT,
) -> bool:
    """Whether relative standing alone earns this name an entry.

    Used when the absolute score falls short. Every hard gate still applies
    afterwards, so this widens the candidate pool without weakening risk control.
    """

    if int(getattr(report, "universe_size", 0) or 0) < MIN_RANKED_UNIVERSE:
        return False
    return float(getattr(report, "universe_percentile", 0.0) or 0.0) >= entry_percentile


def chase_reason(
    report: ComprehensiveAnalysisReport,
    buzz: Optional[object] = None,
) -> str:
    """Why buying today would be chasing, or "" when entry timing is fine.

    Deliberately independent of the composite score: "it already ran today" is a
    timing question, and diluting it into a low-weight factor let a +22% day
    still clear the entry threshold.
    """

    financials = report.financials
    change = float(financials.price_change_pct or 0.0)
    if change >= CHASE_DAY_PCT:
        return f"今日已涨 {change:+.1f}%，超过 {CHASE_DAY_PCT:.0f}% 追高阈值，今天不是买点"

    low = float(financials.fifty_two_week_low or 0.0)
    high = float(financials.fifty_two_week_high or 0.0)
    price = float(financials.price or 0.0)
    if high > low > 0.0 and price > 0.0:
        position = (price - low) / (high - low) * 100.0
        if position >= CHASE_RANGE_PCT:
            return f"处于52周区间 {position:.0f}% 分位，上行空间已被大量定价"

    # Crowding: top-10 on Reddit AND still accelerating. Treated as a reason to
    # wait, never as confirmation — the one rigorous audit of finance-influencer
    # calls found 45% directional accuracy across ~18k predictions.
    if buzz is not None and getattr(buzz, "is_crowded", False):
        return (
            f"社交热度第 {buzz.rank} 位且提及量放大 {buzz.surge_ratio:.1f}x，"
            "属于拥挤交易，等热度消退再看"
        )
    return ""


def valuation_block_reason(report: ComprehensiveAnalysisReport) -> str:
    """Why the valuation forbids an entry, or "" when it does not.

    The threshold is **relative to the universe** rather than a fixed -10%.

    A fixed line encodes an assumption about the absolute level of the market. It
    survived only because the old DCF systematically overstated intrinsic value;
    once it was corrected to normalised owner earnings, measured live, all 17
    AI-chain names priced below the line and the gate blocked the entire
    universe every day — indistinguishable from the strategy being switched off.

    A DCF is a point estimate resting on a discount rate and a growth fade, so
    the level it produces is far less trustworthy than the *ordering* it produces.
    Gating on relative position uses the part that is reliable. `VALUATION_FLOOR`
    still catches the genuinely absurd, where the model itself has broken down.
    """

    valuation = report.valuation
    if not getattr(valuation, "is_reliable", True):
        return ""
    mos = valuation.margin_of_safety_pct
    if mos <= VALUATION_FLOOR_PCT:
        return (
            f"安全边际 {mos:+.1f}%，内在价值 {valuation.intrinsic_value_dcf:.2f} "
            f"远低于现价 {report.financials.price:.2f}，估值不支持买入"
        )
    percentile = float(getattr(report, "valuation_percentile", -1.0))
    if 0.0 <= percentile < VALUATION_MIN_PERCENTILE:
        return (
            f"安全边际 {mos:+.1f}%，在同批标的中仅排第 {percentile:.0f} 分位，"
            "相对其他候选更贵"
        )
    return ""


def entry_block_reason(
    report: ComprehensiveAnalysisReport,
    buzz: Optional[object] = None,
) -> str:
    """Every hard gate that blocks *adding*, as one reason string.

    ETFs skip the fundamental gate: an index has no issuer income statement to
    discount, so a DCF on it is meaningless. Price-action gates still apply.
    """

    if bool(getattr(report.financials, "is_etf", False)):
        return chase_reason(report, buzz)

    chase = chase_reason(report, buzz)
    if chase:
        return chase

    valuation = valuation_block_reason(report)
    if valuation:
        return valuation

    momentum = report.quant_factors.momentum_score
    if momentum < 40.0:
        notes = "；".join(report.quant_factors.momentum_notes)
        return f"动量 {momentum:.1f} 偏弱（{notes}）"
    return ""
