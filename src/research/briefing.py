"""AI supply-chain daily briefing.

Composes the pieces that already exist into one decision document:

* screener  -> which AI-supply-chain names are liquid enough to trade today
* venue     -> the price an order would actually fill at
* analysis  -> deterministic scores, valuation, chokepoint, redlines
* news      -> headlines with evidence ids
* holdings  -> cost basis, so "add / hold / trim" is judged against entry price
* LLM       -> a citation-constrained rationale over the above

The LLM is optional and never invents inputs: it receives only the evidence
assembled here, and its output is discarded if it cites anything outside the
supplied evidence ids. With no model configured the briefing still renders from
the deterministic engines.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from ..core.orchestrator import ComprehensiveAnalysisReport
from ..core.gates import (
    CHASE_DAY_PCT,
    CHASE_RANGE_PCT,
    ETF_POSITION_CAP_PCT,
    MIN_RANKED_UNIVERSE,
    TOP_QUANTILE_PCT,
    chase_reason as _chase_reason,
    valuation_block_reason,
)
from ..data.attention import AttentionResult, BuzzEntry, NewsSentiment, crowding_note


@dataclass
class SegmentSummary:
    segment: str
    label: str
    role: str
    candidate_count: int
    analysed: List[str] = field(default_factory=list)
    average_score: float = 0.0
    average_change_pct: float = 0.0
    best_ticker: str = ""
    best_score: float = 0.0


@dataclass
class BriefingIdea:
    ticker: str
    name: str
    segment: str
    segment_label: str
    action: str            # ADD / HOLD / TRIM / AVOID
    score: float
    recommendation: str
    price: float
    change_pct: float
    momentum_score: float
    momentum_notes: List[str] = field(default_factory=list)
    margin_of_safety_pct: float = 0.0
    chokepoint_level: int = 0
    position_cap_pct: float = 0.0
    held_quantity: float = 0.0
    average_cost: float = 0.0
    unrealised_pct: float = 0.0
    weight_pct: float = 0.0
    reasons: List[str] = field(default_factory=list)
    news: List[Dict[str, Any]] = field(default_factory=list)
    ai_summary: str = ""
    ai_action_bias: str = ""
    ai_confidence: float = 0.0
    ai_citations: List[str] = field(default_factory=list)
    # Social attention and news sentiment. Reported as context and a crowding
    # warning; never used to justify an entry on their own.
    buzz_rank: int = 0
    buzz_mentions: int = 0
    buzz_delta: int = 0
    buzz_surge_ratio: float = 0.0
    buzz_crowded: bool = False
    buzz_note: str = ""
    news_score: float = 0.0
    news_label: str = ""
    news_article_count: int = 0
    news_available: bool = False
    # Headlines behind `news_score`. These come from Google News RSS and are the
    # feed that actually carries company events ("Nvidia Just Paused Part of Its
    # AI Financing Machine"). They were fetched, compressed into one float, then
    # discarded — so the most informative source in the pipeline reached neither
    # the screen nor the model's evidence pool.
    news_drivers: List[Dict[str, Any]] = field(default_factory=list)
    # 1y downsampled closes, for the trend sparkline.
    price_history: List[Dict[str, Any]] = field(default_factory=list)
    fifty_two_week_low: float = 0.0
    fifty_two_week_high: float = 0.0
    # Relative standing within the run. The absolute score barely moves day to
    # day (45% of it is quarterly filings), so rank is the field that actually
    # carries new information between briefings.
    universe_percentile: float = 0.0
    universe_size: int = 0
    valuation_percentile: float = -1.0


@dataclass
class DailyBriefing:
    generated_at_utc: str
    trading_date: str
    segments: List[SegmentSummary] = field(default_factory=list)
    ideas: List[BriefingIdea] = field(default_factory=list)
    portfolio: Dict[str, Any] = field(default_factory=dict)
    market_note: str = ""
    ai_status: str = "disabled"
    ai_error: str = ""
    screened: Dict[str, Any] = field(default_factory=dict)
    attention_errors: Dict[str, str] = field(default_factory=dict)
    buzz_universe_size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at_utc": self.generated_at_utc,
            "trading_date": self.trading_date,
            "segments": [asdict(item) for item in self.segments],
            "ideas": [asdict(item) for item in self.ideas],
            "portfolio": self.portfolio,
            "market_note": self.market_note,
            "ai_status": self.ai_status,
            "ai_error": self.ai_error,
            "screened": self.screened,
            "attention_errors": self.attention_errors,
            "buzz_universe_size": self.buzz_universe_size,
        }


# Entry gates (chase thresholds, ETF cap) live in ``core.gates`` so the order
# planner applies exactly the same rules. They used to be defined here, private
# to the briefing, which let the two surfaces disagree about the same ticker.


def classify_action(
    report: ComprehensiveAnalysisReport,
    *,
    held_quantity: float,
    weight_pct: float,
    minimum_score: float = 60.0,
    buzz: Optional[BuzzEntry] = None,
    entry_percentile: float = TOP_QUANTILE_PCT,
) -> tuple:
    """Decide ADD / HOLD / TRIM / AVOID and state why.

    Deterministic on purpose: the LLM explains and challenges this call, it does
    not make it. Position caps come from the risk assessment, not the model.

    Entry is granted on **either** an absolute score above ``minimum_score`` or a
    top-30% rank within today's universe. A fixed line alone is a bet that
    the constant is calibrated to the market: measured live across 16 AI-chain
    names, every one scored below 60 once the DCF was corrected, so a pure
    absolute test emitted zero ideas every single day and the briefing was
    unusable. Rank cannot go permanently empty, because something is always
    relatively best — and it *moves*, which a near-static absolute score does not.

    The hard gates below (chase, valuation, momentum) still apply to a
    rank-qualified name, so "best of a bad universe" cannot buy a blow-off top.

    ETFs take a separate path: their cap is wider because they are already
    diversified, and their valuation is skipped because an index has no issuer
    income statement to discount.
    """

    reasons: List[str] = []
    score = report.final_composite_score
    financials = report.financials
    percentile = float(getattr(report, "universe_percentile", 0.0) or 0.0)
    universe_size = int(getattr(report, "universe_size", 0) or 0)
    is_etf = bool(getattr(financials, "is_etf", False))
    cap = (
        ETF_POSITION_CAP_PCT if is_etf
        else report.risk_assessment.recommended_max_allocation_pct
    )
    held = held_quantity > 0.0
    # Ranking needs a real cross-section to mean anything; below that, fall back
    # to the absolute line alone rather than crowning the best of three.
    ranked = universe_size >= MIN_RANKED_UNIVERSE
    qualifies_on_rank = ranked and percentile >= entry_percentile

    if is_etf:
        # An ETF cannot be judged on ROE or a DCF, so only concentration and
        # price action apply. Saying so is better than scoring it on fields that
        # are structurally zero.
        reasons.append(f"ETF：按分散化标的处理，仓位上限 {cap:.0f}%")
        if held and weight_pct > cap + 0.05:
            reasons.append(f"当前仓位 {weight_pct:.2f}% 超过 ETF 上限 {cap:.0f}%")
            return "TRIM", reasons
        chase = _chase_reason(report, buzz)
        if chase:
            reasons.append(chase)
            return ("HOLD" if held else "AVOID"), reasons
        reasons.append("估值与基本面引擎对指数不适用，仅依据仓位与价格位置")
        return ("HOLD" if held else "ADD"), reasons

    if score < minimum_score and not qualifies_on_rank:
        if ranked:
            reasons.append(
                f"综合分 {score:.1f} 低于 {minimum_score:.0f} 分入场线，"
                f"且仅排在同批 {universe_size} 只中的第 {percentile:.0f} 分位"
            )
        else:
            reasons.append(f"综合分 {score:.1f} 低于 {minimum_score:.0f} 分入场线")
        if held:
            reasons.append("已持有且评分不足，应减仓")
            return "TRIM", reasons
        return "AVOID", reasons

    if held and weight_pct > cap + 0.05:
        reasons.append(f"当前仓位 {weight_pct:.2f}% 超过上限 {cap:.1f}%")
        return "TRIM", reasons

    if held and weight_pct >= cap - 0.05:
        reasons.append(f"仓位 {weight_pct:.2f}% 已接近上限 {cap:.1f}%")
        return "HOLD", reasons

    # Hard chase gate, evaluated before any ADD is allowed.
    chase = _chase_reason(report, buzz)
    if chase:
        reasons.append(chase)
        return ("HOLD" if held else "AVOID"), reasons

    # A negative margin of safety means the DCF says it is already expensive.
    expensive = valuation_block_reason(report)
    if expensive:
        reasons.append(expensive)
        return ("HOLD" if held else "AVOID"), reasons

    momentum = report.quant_factors.momentum_score
    if momentum < 40.0:
        reasons.append(f"动量 {momentum:.1f} 偏弱（{'；'.join(report.quant_factors.momentum_notes)}）")
        return ("HOLD" if held else "AVOID"), reasons

    reasons.append(
        f"综合分 {score:.1f}"
        + (f"（同批 {universe_size} 只中第 {percentile:.0f} 分位）" if ranked else "")
        + f"，仓位上限 {cap:.1f}%"
    )
    if score < minimum_score and qualifies_on_rank:
        # Be explicit that this is a relative call, not an absolute bargain.
        reasons.append(
            f"注意：未达 {minimum_score:.0f} 分绝对线，入选理由是相对排名靠前，"
            "属于矮子里拔将军"
        )
    if report.quant_factors.momentum_notes:
        reasons.append("；".join(report.quant_factors.momentum_notes))
    if report.valuation.margin_of_safety_pct < 0:
        reasons.append(
            f"注意：安全边际 {report.valuation.margin_of_safety_pct:+.1f}%，估值已偏贵"
        )
    return "ADD", reasons


BRIEFING_SYSTEM = (
    "你是一名美股 AI 产业链研究员。你只依据提供的证据写结论，"
    "不引入外部记忆或未提供的事实。你的判断要具体、可反驳，"
    "并明确指出最可能让这个判断失效的条件。禁止空话和两头讨好。"
)

BRIEFING_PROMPT = """基于以下证据，为今日 AI 产业链埋伏给出结论。

组合现状：
{portfolio}

分段扫描：
{segments}

候选标的（含确定性评分、成本价与新闻）：
{ideas}

要求返回单个 JSON 对象：
{{
  "market_note": "<=3 句：今日 AI 产业链整体处境，只用上面的数据",
  "picks": [
    {{
      "ticker": "...",
      "conviction": "high|medium|low",
      "rationale": "<=3 句，必须说明为什么是现在、以及和成本价的关系",
      "invalidation": "什么情况证明这个判断错了",
      "citations": ["新闻 evidence_id，只能用上面出现过的"]
    }}
  ]
}}

规则：
- 只讨论上面列出的标的，不要引入其他公司。
- 已持仓的标的必须结合成本价和浮动盈亏来判断加仓还是减仓。
- social_* 字段是 Reddit 关注度，只能当拥挤度/情绪指标；社交热度高不构成买入理由，
  反而要提示接盘风险（对 51 个财经大V 约 1.8 万条预测的审计显示方向准确率仅 45%）。
- 证据不足就直说，conviction 用 low。
- citations 只能引用上面出现过的 evidence_id，不得编造。
"""


class BriefingComposer:
    """Assembles the briefing; the LLM layer is injected and optional."""

    def __init__(self, ai_service=None):
        self.ai_service = ai_service

    def compose(
        self,
        *,
        reports: Sequence[ComprehensiveAnalysisReport],
        screened: Dict[str, Any],
        account: Optional[Dict[str, Any]] = None,
        minimum_score: float = 60.0,
        attention: Optional[AttentionResult] = None,
    ) -> DailyBriefing:
        account = account or {}
        positions = {
            str(item.get("ticker", "")): item for item in account.get("positions", [])
        }
        by_ticker = {
            str(item.get("ticker", "")): item
            for item in screened.get("shortlist", [])
        }

        briefing = DailyBriefing(
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            trading_date=datetime.now(timezone.utc).date().isoformat(),
            screened={
                "total_listings": screened.get("total_listings", 0),
                "tradable_listings": screened.get("tradable_listings", 0),
                "shortlist_size": len(screened.get("shortlist", [])),
            },
        )

        # Per-segment roll-up from the analysed names.
        segment_rows: Dict[str, List[ComprehensiveAnalysisReport]] = {}
        for report in reports:
            meta = by_ticker.get(report.financials.ticker, {})
            segment = str(meta.get("segment", "")) or "unclassified"
            segment_rows.setdefault(segment, []).append(report)

        catalogue = {
            item["id"]: item for item in screened.get("segment_catalogue", [])
        }
        for segment, rows in sorted(segment_rows.items()):
            spec = catalogue.get(segment, {})
            scores = [row.final_composite_score for row in rows]
            changes = [row.financials.price_change_pct for row in rows]
            best = max(rows, key=lambda row: row.final_composite_score)
            all_candidates = screened.get("segments", {}).get(segment, [])
            briefing.segments.append(SegmentSummary(
                segment=segment,
                label=str(spec.get("label", segment)),
                role=str(spec.get("role", "")),
                candidate_count=len(all_candidates),
                analysed=[row.financials.ticker for row in rows],
                average_score=round(sum(scores) / len(scores), 1) if scores else 0.0,
                average_change_pct=round(sum(changes) / len(changes), 2) if changes else 0.0,
                best_ticker=best.financials.ticker,
                best_score=best.final_composite_score,
            ))

        for report in reports:
            ticker = report.financials.ticker
            meta = by_ticker.get(ticker, {})
            position = positions.get(ticker, {})
            held = float(position.get("quantity", 0.0))
            weight = float(position.get("weight_pct", 0.0))
            buzz = (attention.buzz.get(ticker) if attention else None)
            news = (attention.sentiment.get(ticker) if attention else None)
            action, reasons = classify_action(
                report,
                held_quantity=held,
                weight_pct=weight,
                minimum_score=minimum_score,
                buzz=buzz,
            )
            news_items = [
                {
                    "evidence_id": item.get("evidence_id", ""),
                    "title": item.get("title", ""),
                    "publisher": item.get("publisher", ""),
                    "url": item.get("url", ""),
                }
                for item in (asdict(report.news).get("items") or [])[:4]
            ]
            briefing.ideas.append(BriefingIdea(
                ticker=ticker,
                name=report.financials.name,
                segment=str(meta.get("segment", "")),
                segment_label=str(meta.get("segment_label", "")),
                action=action,
                score=report.final_composite_score,
                recommendation=report.overall_recommendation,
                price=report.financials.price,
                change_pct=report.financials.price_change_pct,
                momentum_score=report.quant_factors.momentum_score,
                momentum_notes=list(report.quant_factors.momentum_notes),
                margin_of_safety_pct=report.valuation.margin_of_safety_pct,
                chokepoint_level=report.chokepoint.chokepoint_level,
                position_cap_pct=report.risk_assessment.recommended_max_allocation_pct,
                held_quantity=held,
                average_cost=float(position.get("average_cost", 0.0)),
                unrealised_pct=float(position.get("return_pct", 0.0)),
                weight_pct=weight,
                reasons=reasons,
                news=news_items,
                buzz_rank=(buzz.rank if buzz else 0),
                buzz_mentions=(buzz.mentions if buzz else 0),
                buzz_delta=(buzz.mention_delta if buzz else 0),
                buzz_surge_ratio=(round(buzz.surge_ratio, 2) if buzz else 0.0),
                buzz_crowded=(buzz.is_crowded if buzz else False),
                buzz_note=crowding_note(buzz),
                news_score=(news.score if news else 0.0),
                news_label=(news.label if news else ""),
                news_article_count=(news.article_count if news else 0),
                news_available=(bool(news and news.available)),
                news_drivers=[
                    {
                        "title": str(item.get("title", ""))[:220],
                        "source": str(item.get("source", "")),
                        "url": str(item.get("url", "")),
                    }
                    for item in ((news.top_headlines if news else []) or [])[:5]
                ],
                price_history=list(getattr(report.financials, "price_history", []) or []),
                fifty_two_week_low=float(report.financials.fifty_two_week_low or 0.0),
                fifty_two_week_high=float(report.financials.fifty_two_week_high or 0.0),
                universe_percentile=float(getattr(report, "universe_percentile", 0.0) or 0.0),
                universe_size=int(getattr(report, "universe_size", 0) or 0),
                valuation_percentile=float(getattr(report, "valuation_percentile", -1.0)),
            ))

        # Rank actionable ideas first, then by score.
        order = {"ADD": 0, "TRIM": 1, "HOLD": 2, "AVOID": 3}
        briefing.ideas.sort(key=lambda item: (order.get(item.action, 9), -item.score))

        briefing.portfolio = {
            "equity": account.get("equity", 0.0),
            "holdings_value": account.get("holdings_value", 0.0),
            "total_cost": account.get("total_cost", 0.0),
            "unrealised_pnl": account.get("unrealised_pnl", 0.0),
            "unrealised_pnl_pct": account.get("unrealised_pnl_pct", 0.0),
            "realised_pnl": account.get("realised_pnl", 0.0),
            "earn_total_usdt": account.get("earn_total_usdt", 0.0),
            "net_worth": account.get("net_worth", 0.0),
            "position_count": len(positions),
        }
        if attention is not None:
            briefing.attention_errors = dict(attention.errors)
            briefing.buzz_universe_size = attention.buzz_universe_size
        self._attach_ai(briefing)
        return briefing

    def _attach_ai(self, briefing: DailyBriefing) -> None:
        if self.ai_service is None:
            briefing.ai_status = "disabled"
            return
        allowed = {
            item["evidence_id"]
            for idea in briefing.ideas
            for item in idea.news
            if item.get("evidence_id")
        }
        evidence = {
            "portfolio": briefing.portfolio,
            "segments": [asdict(item) for item in briefing.segments],
            "ideas": [
                {
                    "ticker": idea.ticker,
                    "segment": idea.segment_label,
                    "action": idea.action,
                    "score": idea.score,
                    "price": idea.price,
                    "change_pct": idea.change_pct,
                    "momentum": idea.momentum_score,
                    "momentum_notes": idea.momentum_notes,
                    "margin_of_safety_pct": idea.margin_of_safety_pct,
                    "held_quantity": idea.held_quantity,
                    "average_cost": idea.average_cost,
                    "unrealised_pct": idea.unrealised_pct,
                    "reasons": idea.reasons,
                    "news": idea.news,
                    "social_rank": idea.buzz_rank,
                    "social_mentions": idea.buzz_mentions,
                    "social_surge_ratio": idea.buzz_surge_ratio,
                    "social_crowded": idea.buzz_crowded,
                    "news_sentiment_score": idea.news_score,
                    "news_sentiment_label": idea.news_label,
                    # Real headlines, so the model reasons about events rather
                    # than only about a sentiment float it cannot interrogate.
                    "recent_headlines": [
                        item.get("title", "") for item in idea.news_drivers
                    ],
                }
                for idea in briefing.ideas
            ],
        }
        try:
            result = self.ai_service.synthesize_briefing(evidence, allowed)
        except Exception as error:  # provider failures must not break the report
            briefing.ai_status = "error"
            briefing.ai_error = str(error)[:300]
            return
        if not result or result.get("status") != "ok":
            briefing.ai_status = str((result or {}).get("status", "error"))
            briefing.ai_error = str((result or {}).get("error", ""))[:300]
            return

        briefing.ai_status = "ok"
        briefing.market_note = str(result.get("market_note", ""))[:600]
        picks = {
            str(pick.get("ticker", "")).upper(): pick
            for pick in result.get("picks", [])
            if isinstance(pick, dict)
        }
        for idea in briefing.ideas:
            pick = picks.get(idea.ticker)
            if not pick:
                continue
            idea.ai_summary = str(pick.get("rationale", ""))[:500]
            idea.ai_action_bias = str(pick.get("conviction", "")).lower()
            invalidation = str(pick.get("invalidation", ""))[:300]
            if invalidation:
                idea.ai_summary = f"{idea.ai_summary}\n失效条件：{invalidation}"
            # Citations outside the supplied evidence are dropped, not shown.
            idea.ai_citations = [
                str(value) for value in (pick.get("citations") or [])
                if str(value) in allowed
            ]
            confidence = {"high": 0.85, "medium": 0.6, "low": 0.3}
            idea.ai_confidence = confidence.get(idea.ai_action_bias, 0.0)
