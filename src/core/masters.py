"""Berkshire 4 Masters & AI Hedge Fund Multi-Agent Debate Engine."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Any
from ..data.fetcher import CompanyFinancials


@dataclass
class MasterVote:
    name: str
    role: str
    conviction: float  # -1.0 (Strong Sell) to +1.0 (Strong Buy)
    score: float       # 1.0 to 5.0
    key_thesis: str
    primary_concern: str
    verdict: str  # PASS / BUY / HOLD / SELL


@dataclass
class MasterDebateResult:
    ticker: str
    votes: List[MasterVote]
    consensus_score: float
    consensus_verdict: str
    mirror_test_summary: str  # 5-sentence Duan Yongping mirror test
    munger_inversion_summary: str  # What kills the company?


class MastersDebateEngine:
    """Executes multi-perspective adversarial debates among legendary investor personas."""

    def debate(self, data: CompanyFinancials) -> MasterDebateResult:
        sym = data.ticker.upper()
        votes: List[MasterVote] = []

        # 1. Warren Buffett Agent
        buffett_score = self._eval_buffett(data)
        votes.append(buffett_score)

        # 2. Charlie Munger Agent
        munger_score = self._eval_munger(data)
        votes.append(munger_score)

        # 3. Duan Yongping Agent
        duan_score = self._eval_duan(data)
        votes.append(duan_score)

        # 4. Li Lu Agent
        lilu_score = self._eval_lilu(data)
        votes.append(lilu_score)

        # 5. Bill Ackman Agent
        ackman_score = self._eval_ackman(data)
        votes.append(ackman_score)

        # 6. Cathie Wood Agent
        wood_score = self._eval_wood(data)
        votes.append(wood_score)

        avg_score = sum(v.score for v in votes) / len(votes)
        avg_conviction = sum(v.conviction for v in votes) / len(votes)

        if avg_conviction >= 0.5:
            consensus_verdict = "STRONG BUY"
        elif avg_conviction >= 0.15:
            consensus_verdict = "BUY / ACCUMULATE"
        elif avg_conviction >= -0.15:
            consensus_verdict = "HOLD / WATCHLIST"
        else:
            consensus_verdict = "PASS / AVOID"

        mirror_test = self._get_mirror_test(sym, data)
        munger_inversion = self._get_inversion(sym, data)

        return MasterDebateResult(
            ticker=sym,
            votes=votes,
            consensus_score=round(avg_score, 2),
            consensus_verdict=consensus_verdict,
            mirror_test_summary=mirror_test,
            munger_inversion_summary=munger_inversion
        )

    # ------------------------------------------------------------------
    # Each master is expressed as a function of observable financials.
    #
    # Previously these were ticker if/elif chains covering 5 names, so every
    # other symbol received an identical 3.12 consensus — 25% of the final score
    # was a constant for essentially the whole market. The prose is now generated
    # from the same numbers that drive the score, so a verdict is always
    # attributable.
    # ------------------------------------------------------------------

    @staticmethod
    def _scale(value: float, low: float, high: float) -> float:
        """Map value in [low, high] onto 0..1, clamped."""

        if high <= low:
            return 0.0
        return min(max((value - low) / (high - low), 0.0), 1.0)

    @staticmethod
    def _verdict(score: float) -> str:
        if score >= 4.2:
            return "STRONG BUY"
        if score >= 3.6:
            return "BUY"
        if score >= 2.8:
            return "HOLD"
        return "PASS"

    def _eval_buffett(self, d: CompanyFinancials) -> MasterVote:
        """Durable moat and owner earnings: ROE, margin, cash conversion, price."""

        roe = self._scale(d.roe, 0.08, 0.30)
        margin = self._scale(d.operating_margin, 0.05, 0.35)
        cash = self._scale(d.fcf_yield, 0.01, 0.07)
        # Buffett is price-sensitive: a great business at any price is not a buy.
        cheap = 1.0 - self._scale(d.pe, 12.0, 45.0)
        leverage = 1.0 - self._scale(d.debt_to_equity, 0.5, 2.5)
        raw = roe * 0.30 + margin * 0.20 + cash * 0.20 + cheap * 0.20 + leverage * 0.10
        score = round(1.0 + raw * 4.0, 2)
        return MasterVote(
            name="Warren Buffett",
            role="Durable Moat & Owner Earnings",
            conviction=round((raw - 0.5) * 2.0, 2),
            score=score,
            key_thesis=(
                f"ROE {d.roe*100:.1f}%，营业利润率 {d.operating_margin*100:.1f}%，"
                f"自由现金流收益率 {d.fcf_yield*100:.1f}%，P/E {d.pe:.1f}x。"
                + ("现金创造能力与价格都在可接受区间。" if raw >= 0.55
                   else "以当前价格衡量，所有者收益回报不够吸引。")
            ),
            primary_concern=(
                f"负债/权益 {d.debt_to_equity:.2f}，杠杆偏高" if d.debt_to_equity > 1.5
                else (f"P/E {d.pe:.1f}x 已反映较高预期" if d.pe > 30
                      else "需确认十年后仍有同样的定价权"),
            ),
            verdict=self._verdict(score),
        )

    def _eval_munger(self, d: CompanyFinancials) -> MasterVote:
        """Inversion: what kills it. Weighted toward downside and leverage."""

        leverage_risk = self._scale(d.debt_to_equity, 0.3, 2.5)
        volatility_risk = self._scale(d.beta, 1.0, 2.5)
        thin_margin_risk = 1.0 - self._scale(d.operating_margin, 0.03, 0.30)
        rich_price_risk = self._scale(d.pe, 20.0, 60.0)
        risk = (
            leverage_risk * 0.30 + volatility_risk * 0.25
            + thin_margin_risk * 0.25 + rich_price_risk * 0.20
        )
        score = round(1.0 + (1.0 - risk) * 4.0, 2)
        drivers = []
        if leverage_risk > 0.5:
            drivers.append(f"负债/权益 {d.debt_to_equity:.2f}")
        if volatility_risk > 0.5:
            drivers.append(f"Beta {d.beta:.2f}")
        if thin_margin_risk > 0.5:
            drivers.append(f"营业利润率仅 {d.operating_margin*100:.1f}%")
        if rich_price_risk > 0.5:
            drivers.append(f"P/E {d.pe:.1f}x")
        return MasterVote(
            name="Charlie Munger",
            role="Inversion & Downside Analysis",
            conviction=round((1.0 - risk - 0.5) * 2.0, 2),
            score=score,
            key_thesis=(
                "下行风险可控：杠杆、波动与利润率都在可接受范围。" if risk < 0.4
                else "存在明确的致死路径，需要更高的补偿才值得承担。"
            ),
            primary_concern=("；".join(drivers) if drivers else "周期与技术替代风险"),
            verdict=self._verdict(score),
        )

    def _eval_duan(self, d: CompanyFinancials) -> MasterVote:
        """Business model clarity: gross margin durability and simplicity."""

        gross = self._scale(d.gross_margin, 0.25, 0.75)
        operating = self._scale(d.operating_margin, 0.05, 0.35)
        # A business whose sales grow while margins hold is simple to explain.
        growth = self._scale(d.revenue_growth_yoy, 0.0, 0.30)
        raw = gross * 0.40 + operating * 0.35 + growth * 0.25
        score = round(1.0 + raw * 4.0, 2)
        return MasterVote(
            name="段永平",
            role="Business Model & Mirror Test",
            conviction=round((raw - 0.5) * 2.0, 2),
            score=score,
            key_thesis=(
                f"毛利率 {d.gross_margin*100:.1f}% 说明产品有差异化；" if d.gross_margin >= 0.5
                else f"毛利率仅 {d.gross_margin*100:.1f}%，产品接近同质化；"
            ) + f"营收增速 {d.revenue_growth_yoy*100:.1f}%。",
            primary_concern=(
                "增速放缓时利润率能否守住" if d.revenue_growth_yoy < 0.10
                else "高增速是否依赖持续的费用投入"
            ),
            verdict=self._verdict(score),
        )

    def _eval_lilu(self, d: CompanyFinancials) -> MasterVote:
        """Long-horizon compounding at a sane price."""

        quality = self._scale(d.roe, 0.10, 0.28)
        durability = self._scale(d.gross_margin, 0.30, 0.70)
        value = 1.0 - self._scale(d.pe, 10.0, 40.0)
        raw = quality * 0.35 + durability * 0.30 + value * 0.35
        score = round(1.0 + raw * 4.0, 2)
        return MasterVote(
            name="李录",
            role="Long-Horizon Compounding",
            conviction=round((raw - 0.5) * 2.0, 2),
            score=score,
            key_thesis=(
                f"ROE {d.roe*100:.1f}% 搭配 P/E {d.pe:.1f}x，"
                + ("属于可长期持有的复利结构。" if raw >= 0.55
                   else "长期复利空间被当前估值压缩。")
            ),
            primary_concern=(
                f"P/E {d.pe:.1f}x 留给长期回报的空间有限" if d.pe > 30
                else "需要确认竞争格局在十年尺度上稳定"
            ),
            verdict=self._verdict(score),
        )

    def _eval_ackman(self, d: CompanyFinancials) -> MasterVote:
        """Concentrated quality: scale, pricing power, cash generation."""

        scale = self._scale(math.log10(max(d.market_cap, 1e8)), 9.5, 12.0)
        pricing = self._scale(d.operating_margin, 0.10, 0.35)
        cash = self._scale(d.fcf_yield, 0.02, 0.07)
        raw = scale * 0.30 + pricing * 0.40 + cash * 0.30
        score = round(1.0 + raw * 4.0, 2)
        return MasterVote(
            name="Bill Ackman",
            role="Activist Value & Compounder",
            conviction=round((raw - 0.5) * 2.0, 2),
            score=score,
            key_thesis=(
                f"市值 {d.market_cap/1e9:.0f}B，营业利润率 {d.operating_margin*100:.1f}%，"
                f"FCF 收益率 {d.fcf_yield*100:.1f}%。"
                + ("规模与现金流支持集中持仓。" if raw >= 0.55 else "缺乏集中持仓所需的确定性。")
            ),
            primary_concern=(
                "规模不足，缺乏抗冲击能力" if scale < 0.3
                else "需要可执行的价值释放路径"
            ),
            verdict=self._verdict(score),
        )

    def _eval_wood(self, d: CompanyFinancials) -> MasterVote:
        """Disruptive growth: top-line velocity, tolerant of valuation."""

        growth = self._scale(d.revenue_growth_yoy, 0.05, 0.40)
        gross = self._scale(d.gross_margin, 0.30, 0.75)
        # Wood accepts volatility as the price of exposure to change.
        beta_bonus = self._scale(d.beta, 0.8, 2.0) * 0.5
        raw = growth * 0.55 + gross * 0.30 + beta_bonus * 0.15
        score = round(1.0 + raw * 4.0, 2)
        return MasterVote(
            name="Cathie Wood",
            role="Disruptive Innovation",
            conviction=round((raw - 0.5) * 2.0, 2),
            score=score,
            key_thesis=(
                f"营收增速 {d.revenue_growth_yoy*100:.1f}%，毛利率 {d.gross_margin*100:.1f}%。"
                + ("具备指数级扩张的特征。" if raw >= 0.55 else "增长曲线不足以支撑颠覆叙事。")
            ),
            primary_concern=(
                f"增速仅 {d.revenue_growth_yoy*100:.1f}%，颠覆性不明显"
                if d.revenue_growth_yoy < 0.15 else "高估值对执行失误零容忍"
            ),
            verdict=self._verdict(score),
        )

    def _get_mirror_test(self, sym: str, d: CompanyFinancials) -> str:
        """Duan Yongping's mirror test, generated from the company's own numbers.

        Hand-written five-liners for five tickers used to sit here. They read far
        better than anything derived, which was the danger: a confident paragraph
        about TSMC's 2nm ramp was frozen prose that never updated when the
        financials moved, and every other symbol got a generic stub. Prose that
        cannot go stale is prose tied to the data.
        """

        moat = "定价权明确" if d.gross_margin >= 0.5 else (
            "有一定差异化" if d.gross_margin >= 0.35 else "产品接近同质化"
        )
        cash = "现金创造稳定" if d.fcf_yield >= 0.04 else "现金回报有限"
        return (
            f"1. {sym} 属于 {d.sector or '未分类行业'}，{moat}（毛利率 {d.gross_margin*100:.1f}%）。\n"
            f"2. 营收增速 {d.revenue_growth_yoy*100:.1f}%，营业利润率 {d.operating_margin*100:.1f}%。\n"
            f"3. ROE {d.roe*100:.1f}%，负债/权益 {d.debt_to_equity:.2f}。\n"
            f"4. 自由现金流收益率 {d.fcf_yield*100:.1f}%，{cash}。\n"
            f"5. 当前 P/E {d.pe:.1f}x —— 需确认十年后这门生意是否还在同一位置。"
        )

    def _get_inversion(self, sym: str, d: CompanyFinancials) -> str:
        """Munger inversion: name the failure paths this company's numbers imply."""

        paths: List[str] = []
        if d.debt_to_equity > 1.5:
            paths.append(f"负债/权益 {d.debt_to_equity:.2f}，再融资窗口关闭时被迫贱卖资产")
        if d.operating_margin < 0.10:
            paths.append(f"营业利润率仅 {d.operating_margin*100:.1f}%，需求走弱即转亏")
        if d.pe > 40:
            paths.append(f"P/E {d.pe:.1f}x 已定价完美执行，一次不及预期即杀估值")
        if d.beta > 1.8:
            paths.append(f"Beta {d.beta:.2f}，系统性回撤中跌幅会被放大")
        if d.revenue_growth_yoy < 0.0:
            paths.append(f"营收同比 {d.revenue_growth_yoy*100:.1f}%，主业已在收缩")
        if d.gross_margin < 0.30:
            paths.append(f"毛利率 {d.gross_margin*100:.1f}%，缺乏抵御价格战的缓冲")
        if not paths:
            paths.append("财务指标未显示明确致死路径，风险主要来自技术替代与竞争格局变化")
        return "；".join(paths) + "。"
