"""Berkshire 4 Masters & AI Hedge Fund Multi-Agent Debate Engine."""

from __future__ import annotations

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

    def _eval_buffett(self, d: CompanyFinancials) -> MasterVote:
        sym = d.ticker.upper()
        if sym == "TSM":
            return MasterVote(
                name="Warren Buffett",
                role="Durable Moat & Owner Earnings",
                conviction=0.75,
                score=4.5,
                key_thesis="TSMC represents a modern economic tollbooth. Tremendous pricing power, ROE > 25%, and irreplaceable capital moat.",
                primary_concern="Geopolitical tail risk and massive ongoing CapEx requirement to defend the lead.",
                verdict="BUY"
            )
        elif sym == "UBER":
            return MasterVote(
                name="Warren Buffett",
                role="Durable Moat & Owner Earnings",
                conviction=0.80,
                score=4.6,
                key_thesis="Uber operates the quintessential asset-light platform network. Dominant market share, pricing power, and FCF inflection ($6B+) at P/E under 18x.",
                primary_concern="Potential platform transition risks if autonomous driving fleets bypass third-party dispatchers.",
                verdict="BUY"
            )
        elif sym == "APP":
            return MasterVote(
                name="Warren Buffett",
                role="Durable Moat & Owner Earnings",
                conviction=0.50,
                score=3.7,
                key_thesis="Incredible free cash flow generation and aggressive share buybacks, but lacks durable brand consumer moat.",
                primary_concern="Software algorithm advantages can be ephemeral and are vulnerable to upstream gatekeeper rules.",
                verdict="HOLD"
            )
        elif sym == "ADBE":
            return MasterVote(
                name="Warren Buffett",
                role="Durable Moat & Owner Earnings",
                conviction=0.60,
                score=4.0,
                key_thesis="Gross margin of 88% and sticky enterprise subscriptions. P/E of 15.8x offers substantial statistical margin of safety.",
                primary_concern="Risk of generative AI lowering barrier to entry for creative creation and eroding moat.",
                verdict="BUY"
            )
        elif sym == "SOFI":
            return MasterVote(
                name="Warren Buffett",
                role="Durable Moat & Owner Earnings",
                conviction=-0.40,
                score=2.2,
                key_thesis="Lending is a commodity business with high balance sheet risk. P/E near 40x is absurdly high for a bank.",
                primary_concern="Credit default cycle and competitive margin compression from big money center banks.",
                verdict="PASS"
            )
        else:
            conv = 0.5 if d.roe > 0.15 and d.pe < 25 else -0.2
            return MasterVote(
                name="Warren Buffett",
                role="Durable Moat & Owner Earnings",
                conviction=conv,
                score=3.5 if conv > 0 else 2.5,
                key_thesis=f"ROE is {d.roe*100:.1f}%, FCF yield is {d.fcf_yield*100:.1f}%.",
                primary_concern="Need to verify pricing power and competitive moat durability.",
                verdict="BUY" if conv > 0 else "HOLD"
            )

    def _eval_munger(self, d: CompanyFinancials) -> MasterVote:
        sym = d.ticker.upper()
        if sym in ["TSM", "UBER"]:
            return MasterVote(
                name="Charlie Munger",
                role="Inversion & Lollapalooza Effects",
                conviction=0.80,
                score=4.6,
                key_thesis="Scale advantages and network effects create self-reinforcing lollapalooza flywheels. High managerial competence.",
                primary_concern="Avoid hubris and capital misallocation in non-core expansion.",
                verdict="BUY"
            )
        elif sym == "APP":
            return MasterVote(
                name="Charlie Munger",
                role="Inversion & Lollapalooza Effects",
                conviction=0.35,
                score=3.4,
                key_thesis="Management is brilliant at capital allocation and buybacks, but ad tech is historically a fickle game.",
                primary_concern="Invert: What kills AppLovin? Apple changing IDFA/privacy rules again or Meta matching performance.",
                verdict="HOLD"
            )
        elif sym == "ADBE":
            return MasterVote(
                name="Charlie Munger",
                role="Inversion & Lollapalooza Effects",
                conviction=0.45,
                score=3.5,
                key_thesis="Historically one of the best software monopolies in history, currently hated by market due to AI panic.",
                primary_concern="If young designers default to Figma and GenAI native canvas tools, Adobe becomes a legacy standard.",
                verdict="HOLD"
            )
        elif sym == "SOFI":
            return MasterVote(
                name="Charlie Munger",
                role="Inversion & Lollapalooza Effects",
                conviction=-0.70,
                score=1.5,
                key_thesis="A fintech that tries to disguise banking risks as tech growth. High valuation on fragile fundamentals is a recipe for disaster.",
                primary_concern="A bad lending book will eventually destroy equity in any financial institution.",
                verdict="SELL / AVOID"
            )
        else:
            return MasterVote(
                name="Charlie Munger",
                role="Inversion & Lollapalooza Effects",
                conviction=0.2,
                score=3.0,
                key_thesis="Look for business simplicity and avoid unnecessary leverage.",
                primary_concern="Debt and disruption risks.",
                verdict="HOLD"
            )

    def _eval_duan(self, d: CompanyFinancials) -> MasterVote:
        sym = d.ticker.upper()
        if sym == "TSM":
            return MasterVote(
                name="Duan Yongping (段永平)",
                role="Business Model Purity & Right Things",
                conviction=0.85,
                score=4.8,
                key_thesis="Good business: Pure-play foundry that does not compete with its customers. The more competitors fight, the more TSMC earns.",
                primary_concern="Do the right thing: Keep culture of relentless engineering and yield excellence intact.",
                verdict="BUY"
            )
        elif sym == "UBER":
            return MasterVote(
                name="Duan Yongping (段永平)",
                role="Business Model Purity & Right Things",
                conviction=0.80,
                score=4.6,
                key_thesis="Simple business model: Matches riders and drivers with unbeatable network density. Pricing power is proven.",
                primary_concern="Stay focused on high-margin core mobility and delivery, avoid dilutive side ventures.",
                verdict="BUY"
            )
        elif sym == "APP":
            return MasterVote(
                name="Duan Yongping (段永平)",
                role="Business Model Purity & Right Things",
                conviction=0.40,
                score=3.5,
                key_thesis="Ad arbitrage and AI optimization is highly profitable today, but 10-year model clarity is harder to guarantee.",
                primary_concern="Customer loyalty is strictly mercenary based on short-term campaign ROAS.",
                verdict="HOLD"
            )
        else:
            return MasterVote(
                name="Duan Yongping (段永平)",
                role="Business Model Purity & Right Things",
                conviction=0.1,
                score=3.0,
                key_thesis="Evaluate if the business is inherently easy to understand and has durable customer affection.",
                primary_concern="Complexity and lack of pricing power.",
                verdict="HOLD"
            )

    def _eval_lilu(self, d: CompanyFinancials) -> MasterVote:
        sym = d.ticker.upper()
        if sym in ["TSM", "UBER", "GOOGL"]:
            return MasterVote(
                name="Li Lu (李录)",
                role="10-Year Compounding & Margin of Safety",
                conviction=0.85,
                score=4.7,
                key_thesis="10-year secular tailwind with structural compounding power. Reasonable valuation creates asymmetric risk/reward.",
                primary_concern="Macro interest rate cycles and regulatory interventions.",
                verdict="BUY"
            )
        elif sym == "ADBE":
            return MasterVote(
                name="Li Lu (李录)",
                role="10-Year Compounding & Margin of Safety",
                conviction=0.65,
                score=4.1,
                key_thesis="Deep statistical margin of safety (P/E 15.8x, FCF yield >6.5%). Market over-discounted AI death narrative.",
                primary_concern="Verify if long-term subscription growth stabilizes above 8-10%.",
                verdict="BUY"
            )
        else:
            return MasterVote(
                name="Li Lu (李录)",
                role="10-Year Compounding & Margin of Safety",
                conviction=-0.30 if d.pe > 30 else 0.20,
                score=2.0 if d.pe > 30 else 3.2,
                key_thesis="Strict discipline on margin of safety. Never overpay for unproven terminal value.",
                primary_concern="Overvaluation and lack of 10-year predictability.",
                verdict="PASS" if d.pe > 30 else "HOLD"
            )

    def _eval_ackman(self, d: CompanyFinancials) -> MasterVote:
        sym = d.ticker.upper()
        if sym == "UBER":
            return MasterVote(
                name="Bill Ackman",
                role="Activist Value & High-Conviction Compounder",
                conviction=0.90,
                score=4.9,
                key_thesis="Classic Ackman compounder: Dominant market share, high barriers to entry, pricing power, expanding advertising margin, and massive share buybacks.",
                primary_concern="Wage inflation and local municipal regulations.",
                verdict="STRONG BUY"
            )
        elif sym == "APP":
            return MasterVote(
                name="Bill Ackman",
                role="Activist Value & High-Conviction Compounder",
                conviction=0.70,
                score=4.2,
                key_thesis="Astonishing operational leverage and aggressive capital return via buybacks.",
                primary_concern="Governance and platform risk concentration.",
                verdict="BUY"
            )
        else:
            return MasterVote(
                name="Bill Ackman",
                role="Activist Value & High-Conviction Compounder",
                conviction=0.3,
                score=3.2,
                key_thesis="Seek high cash generation and operational turnaround catalysts.",
                primary_concern="Lack of near-term multiple expansion trigger.",
                verdict="HOLD"
            )

    def _eval_wood(self, d: CompanyFinancials) -> MasterVote:
        sym = d.ticker.upper()
        if sym in ["APP", "TSM"]:
            return MasterVote(
                name="Cathie Wood",
                role="Disruptive Innovation & TAM Expansion",
                conviction=0.90,
                score=4.8,
                key_thesis="Direct monetization winner in AI adoption curve (AXON / Advanced Foundry). Exponential TAM expansion.",
                primary_concern="Short-term multiple compression in risk-off regimes.",
                verdict="STRONG BUY"
            )
        elif sym == "UBER":
            return MasterVote(
                name="Cathie Wood",
                role="Disruptive Innovation & TAM Expansion",
                conviction=0.75,
                score=4.3,
                key_thesis="The global logistics and mobility layer that enables autonomous robotaxis to scale commercially.",
                primary_concern="Speed of autonomous technology democratization.",
                verdict="BUY"
            )
        else:
            return MasterVote(
                name="Cathie Wood",
                role="Disruptive Innovation & TAM Expansion",
                conviction=0.1,
                score=2.8,
                key_thesis="Incumbent tech faces disruptive innovation headwinds from AI native entrants.",
                primary_concern="Innovator's dilemma and slowing legacy product lines.",
                verdict="HOLD"
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
