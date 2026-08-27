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
        }


def classify_action(
    report: ComprehensiveAnalysisReport,
    *,
    held_quantity: float,
    weight_pct: float,
    minimum_score: float = 60.0,
) -> tuple:
    """Decide ADD / HOLD / TRIM / AVOID and state why.

    Deterministic on purpose: the LLM explains and challenges this call, it does
    not make it. Position caps come from the risk assessment, not the model.
    """

    reasons: List[str] = []
    score = report.final_composite_score
    cap = report.risk_assessment.recommended_max_allocation_pct
    held = held_quantity > 0.0

    if score < minimum_score:
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

    momentum = report.quant_factors.momentum_score
    if momentum < 40.0:
        reasons.append(f"动量 {momentum:.1f} 偏弱（{'；'.join(report.quant_factors.momentum_notes)}）")
        return ("HOLD" if held else "AVOID"), reasons

    reasons.append(f"综合分 {score:.1f}，仓位上限 {cap:.1f}%")
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
            action, reasons = classify_action(
                report,
                held_quantity=held,
                weight_pct=weight,
                minimum_score=minimum_score,
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
