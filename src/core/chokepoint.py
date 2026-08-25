"""Serenity-Style Supply Chain & Chokepoint (瓶颈) Analysis Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List
from ..data.fetcher import CompanyFinancials


@dataclass
class ChokepointResult:
    ticker: str
    chokepoint_level: int  # 1 (Commodity) to 5 (Absolute Physical Monopoly)
    chokepoint_title: str
    physical_unreplaceability: float  # 0 to 10
    capex_expansion_barrier: float    # 0 to 10
    switching_cost: float             # 0 to 10
    pricing_power: float              # 0 to 10
    value_capture_ratio: float        # 0 to 10
    overall_score: float              # 0 to 10
    bottleneck_diagnosis: str
    key_evidence: List[str] = field(default_factory=list)
    threat_matrix: List[str] = field(default_factory=list)


class ChokepointAnalyzer:
    """Evaluates where a company sits on the supply chain bottleneck ladder."""

    # Specific qualitative profiles for known companies
    _CHOKEPOINT_PROFILES = {
        "TSM": {
            "level": 5,
            "title": "Absolute Physical Manufacturing Chokepoint",
            "unreplaceability": 9.8,
            "capex_barrier": 9.9,
            "switching_cost": 9.5,
            "pricing_power": 9.2,
            "value_capture": 9.6,
            "diagnosis": "Monopoly on leading-edge 3nm/2nm and CoWoS advanced packaging (>90% market share). All AI GPU and ASIC routes must pass through TSMC's fabs.",
            "evidence": [
                ">90% global market share in sub-5nm advanced node manufacturing",
                "Annual CapEx of $30B+ creating an insurmountable capital and yield-rate barrier",
                "Full order backlog from Nvidia, Apple, AMD, Qualcomm, and Cloud ASICs"
            ],
            "threats": [
                "Geopolitical concentration risks in Taiwan Strait",
                "Margin dilution from overseas fab expansion (US, Japan, Europe)"
            ]
        },
        "AVGO": {
            "level": 4,
            "title": "Data Center Interconnect & ASIC Architecture Chokepoint",
            "unreplaceability": 8.8,
            "capex_barrier": 8.5,
            "switching_cost": 9.0,
            "pricing_power": 8.9,
            "value_capture": 8.7,
            "diagnosis": "Dominates high-speed Ethernet switching silicon (Tomahawk/Jericho) and custom AI ASIC co-design for hyperscalers (Google TPU, Meta, etc.).",
            "evidence": [
                ">70% market share in high-end data center Ethernet switching silicon",
                "Custom ASIC co-design partner of choice for top cloud providers",
                "Immense software recurring revenue (VMware) with 95%+ renewal rates"
            ],
            "threats": [
                "Nvidia's proprietary NVLink / InfiniBand ecosystem competition",
                "High revenue concentration in top 3 hyperscaler customers"
            ]
        },
        "UBER": {
            "level": 4,
            "title": "Global Physical Mobility & Dispatch Network Chokepoint",
            "unreplaceability": 8.6,
            "capex_barrier": 8.2,
            "switching_cost": 8.5,
            "pricing_power": 8.4,
            "value_capture": 8.8,
            "diagnosis": "Unbreachable two-sided network liquidity in urban transportation and delivery. The inevitable distribution layer for autonomous fleets (Waymo/Tesla).",
            "evidence": [
                "150M+ monthly active platform consumers across 70+ countries",
                "Cross-selling flywheel between Rides and Uber Eats lowers CAC by 40%",
                "Waymo and other AV operators partner with Uber for demand dispatch instead of building their own app networks"
            ],
            "threats": [
                "Tesla Robotaxi vertical integration risk if Tesla scales standalone app successfully",
                "Regulatory gig-worker classification and wage pressures"
            ]
        },
        "APP": {
            "level": 3,
            "title": "AI Algorithmic Ad-Attribution & In-App Monetization Engine",
            "unreplaceability": 6.8,
            "capex_barrier": 6.0,
            "switching_cost": 6.5,
            "pricing_power": 8.0,
            "value_capture": 8.2,
            "diagnosis": "AXON 2.0 AI recommendation engine delivers industry-leading ROI for mobile and e-commerce advertisers. High cash flow but upstream platform risk.",
            "evidence": [
                "AXON 2.0 expanded advertiser base from mobile games to multi-billion e-commerce campaigns",
                "EBITDA margins exceeding 55% with exceptional free cash flow conversion",
                "Aggressive share buyback program retiring >5% of share count annually"
            ],
            "threats": [
                "Vulnerable to Apple (iOS) and Google (Android) ad privacy policy disruptions (like ATT)",
                "Competitors (Meta Advantage+, Google PMax) narrowing algorithm conversion gap"
            ]
        },
        "ADBE": {
            "level": 3,
            "title": "Enterprise Creative Workflow & Digital Document Standard",
            "unreplaceability": 7.5,
            "capex_barrier": 6.5,
            "switching_cost": 8.8,
            "pricing_power": 7.8,
            "value_capture": 7.5,
            "diagnosis": "Decades of enterprise creative asset standards (PSD, PDF) and deep workflow integration. Defending against generative AI disruption.",
            "evidence": [
                "Deep integration with global agency, print, video, and design production pipelines",
                "Gross margin >88% with vast enterprise contract retention rates",
                "Firefly GenAI embedded directly into Photoshop/Premiere workflows"
            ],
            "threats": [
                "Generative AI native startups (Midjourney, Sora, Runway, Figma) lowering design barrier",
                "Canva eating casual and SMB graphic design demand"
            ]
        },
        "SOFI": {
            "level": 1,
            "title": "Digital Consumer Banking & Lending Platform",
            "unreplaceability": 4.0,
            "capex_barrier": 4.5,
            "switching_cost": 4.5,
            "pricing_power": 4.0,
            "value_capture": 4.2,
            "diagnosis": "High-growth neo-bank with national charter, but essentially sells commoditized money and consumer debt in a hyper-competitive market.",
            "evidence": [
                "Rapid growth in member base and Galileo/Technisys financial technology stack",
                "National bank charter lowers cost of deposits relative to non-bank fintechs"
            ],
            "threats": [
                "Zero true physical barrier: money and credit are fungible commodities",
                "Credit risk, interest rate spreads, and default cycles compress loan book value"
            ]
        }
    }

    def analyze(self, data: CompanyFinancials) -> ChokepointResult:
        sym = data.ticker.upper()
        if sym in self._CHOKEPOINT_PROFILES:
            p = self._CHOKEPOINT_PROFILES[sym]
            score = (p["unreplaceability"] * 0.3 +
                     p["capex_barrier"] * 0.2 +
                     p["switching_cost"] * 0.2 +
                     p["pricing_power"] * 0.15 +
                     p["value_capture"] * 0.15)
            return ChokepointResult(
                ticker=sym,
                chokepoint_level=p["level"],
                chokepoint_title=p["title"],
                physical_unreplaceability=p["unreplaceability"],
                capex_expansion_barrier=p["capex_barrier"],
                switching_cost=p["switching_cost"],
                pricing_power=p["pricing_power"],
                value_capture_ratio=p["value_capture"],
                overall_score=round(score, 2),
                bottleneck_diagnosis=p["diagnosis"],
                key_evidence=p["evidence"],
                threat_matrix=p["threats"]
            )

        # Heuristic fallback based on margins and financials
        unrep = min(max(data.gross_margin * 10, 2.0), 9.0)
        capex = 5.0
        switching = 5.0
        pricing = min(max(data.operating_margin * 20, 2.0), 9.0)
        val_cap = 5.5
        overall = round(unrep * 0.3 + capex * 0.2 + switching * 0.2 + pricing * 0.15 + val_cap * 0.15, 2)
        level = 3 if overall >= 6.5 else (2 if overall >= 5.0 else 1)

        return ChokepointResult(
            ticker=sym,
            chokepoint_level=level,
            chokepoint_title="Generic Technology / Service Position",
            physical_unreplaceability=round(unrep, 1),
            capex_expansion_barrier=capex,
            switching_cost=switching,
            pricing_power=round(pricing, 1),
            value_capture_ratio=val_cap,
            overall_score=overall,
            bottleneck_diagnosis=f"Evaluated with generalized supply chain heuristic. Margin profile indicates Level {level} bottleneck strength.",
            key_evidence=[f"Gross Margin: {data.gross_margin*100:.1f}%", f"Operating Margin: {data.operating_margin*100:.1f}%"],
            threat_matrix=["Competitive entry and technological substitution risks"]
        )
