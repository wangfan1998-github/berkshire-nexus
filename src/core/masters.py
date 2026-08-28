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
        templates = {
            "TSM": "1. TSMC is the world's sole contract manufacturer of sub-3nm chips.\n2. All AI chip designers are its paying customers, not competitors.\n3. Annual $30B+ CapEx ensures no competitor can realistically catch up.\n4. It possesses hard pricing power to pass on inflation.\n5. If the digital world needs compute, TSMC gets paid on every single wafer.",
            "UBER": "1. Uber is the dominant global platform for moving people and food.\n2. Millions of drivers and riders create an insurmountable 2-sided network moat.\n3. The business has flipped into a $6B+ annual free cash flow machine.\n4. Autonomous vehicles need Uber's dispatch network to find paying riders.\n5. Trading at an attractive P/E (<18x) relative to its 15-20% compounding growth rate.",
            "APP": "1. AppLovin operates the highest-converting mobile/e-commerce ad engine (AXON 2.0).\n2. It converts >50% of revenue directly into EBITDA and free cash flow.\n3. Management ruthlessly repurchases and retires shares with excess cash.\n4. However, it operates inside Apple and Google's operating system sandbox.\n5. Excellent high-beta satellite bet, but vulnerable to platform rule changes.",
            "ADBE": "1. Adobe owns the gold standard creative formats (PSD, PDF) across global enterprises.\n2. Its 88% gross margin and subscription model create massive cash generation.\n3. The stock is currently penalized to a 10-year low valuation (P/E ~15.8x).\n4. Generative AI tools like Canva/Midjourney are pressuring entry-level user growth.\n5. High margin of safety value play, awaiting proof that Firefly defends enterprise moat.",
            "SOFI": "1. SoFi is a fast-growing digital financial app with high member growth.\n2. However, its core profits still depend on holding and originating consumer debt.\n3. Money is a commodity and lacks true technological or network switching moats.\n4. High credit risk during economic downturns and rate uncertainty.\n5. Trading at an elevated P/E (>38x) for what is fundamentally a banking business."
        }
        return templates.get(sym, f"1. {sym} operates in {d.sector}.\n2. Revenue growth is {d.revenue_growth_yoy*100:.1f}% with gross margin of {d.gross_margin*100:.1f}%.\n3. P/E ratio is {d.pe:.1f}x with ROE of {d.roe*100:.1f}%.\n4. Free cash flow yield is {d.fcf_yield*100:.1f}%.\n5. Need to confirm sustainable 10-year competitive advantage.")

    def _get_inversion(self, sym: str, d: CompanyFinancials) -> str:
        inversions = {
            "TSM": "Geopolitical conflict in the Taiwan Strait; catastrophic operational delay in 2nm ramp-up; severe margin collapse from overseas fabs.",
            "UBER": "Tesla or Waymo successfully building an independent consumer ride-hailing app with zero commission, disintermediating Uber; extreme regulatory labor reclassification.",
            "APP": "Apple or Google introducing restrictive mobile tracking policies that blind AXON 2.0 attribution; Meta Advantage+ offering free superior ad conversion.",
            "ADBE": "GenAI generative models making pixel-level editing obsolete; enterprise creatives migrating en masse to native browser-based AI suites.",
            "SOFI": "Macro credit shock triggering soaring consumer loan default rates; capital adequacy ratio falling below regulatory requirements; deposit outflow."
        }
        return inversions.get(sym, "Technological obsolescence, loss of pricing power, aggressive leverage, or governance failures.")
