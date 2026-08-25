"""Terminal CLI interface for OmniAlpha Agent (Zero-Dependency ANSI + Rich Support)."""

from __future__ import annotations

import argparse
import sys
from typing import List

from .core.orchestrator import OmniAlphaOrchestrator, ComprehensiveAnalysisReport


# ANSI Color Codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_single_report(r: ComprehensiveAnalysisReport):
    fin = r.financials
    choke = r.chokepoint
    debate = r.masters_debate
    val = r.valuation
    quant = r.quant_factors
    risk = r.risk_assessment

    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║                    🎯 OmniAlpha Executive Investment Memo: {fin.name[:35]:<35} ║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════════════════════════════════════════╝{RESET}")
    print(f"{BOLD}Ticker:{RESET} {CYAN}{fin.ticker}{RESET} | {BOLD}Price:{RESET} ${fin.price:.2f} | {BOLD}P/E:{RESET} {fin.pe:.1f}x | {BOLD}EPS:{RESET} ${fin.eps:.2f} | {BOLD}Beta:{RESET} {fin.beta:.2f} | {BOLD}Sector:{RESET} {fin.sector}\n")

    # Section 1: Score Summary
    print(f"{BOLD}{YELLOW}┌── 📊 Multi-Framework Synthesis Scorecard ──────────────────────────────────────────────────┐{RESET}")
    print(f"│ 1. Serenity Chokepoint (瓶颈) : {CYAN}Level {choke.chokepoint_level}/5 ({choke.overall_score}/10){RESET} - {choke.chokepoint_title}")
    print(f"│ 2. Berkshire 4 Masters (大师) : {YELLOW}{debate.consensus_score}/5.0{RESET} - {debate.consensus_verdict}")
    print(f"│ 3. Graham / DCF Valuation (估值) : {GREEN}MoS {val.margin_of_safety_pct:+.1f}%{RESET} (Intrinsic: ${val.intrinsic_value_dcf:.2f}) - {val.valuation_status}")
    print(f"│ 4. Qlib Multi-Factor Alpha (量化): {MAGENTA}{quant.composite_alpha_score}/100{RESET} (Q:{quant.quality_score} V:{quant.value_score} G:{quant.growth_score} M:{quant.momentum_score})")
    print(f"│ 5. Final OmniAlpha Score     : {BOLD}{YELLOW}{r.final_composite_score} / 100{RESET} ──► {BOLD}{GREEN}{r.overall_recommendation}{RESET}")
    print(f"│ 6. Risk & Position Sizing    : Max Allocation {BOLD}{YELLOW}{risk.recommended_max_allocation_pct:.1f}%{RESET} ({risk.portfolio_role})")
    print(f"{BOLD}{YELLOW}└────────────────────────────────────────────────────────────────────────────────────────────┘{RESET}\n")

    # Section 2: Mirror Test & Inversion
    print(f"{BOLD}{GREEN}🔍 段永平 5 句话镜子测试 (5-Sentence Mirror Test):{RESET}")
    for line in debate.mirror_test_summary.split("\n"):
        print(f"  {DIM}•{RESET} {line}")
    print()

    print(f"{BOLD}{RED}💀 查理·芒格 逆向思考 (Munger Inversion - 什么情况会让它死?):{RESET}")
    print(f"  {YELLOW}{debate.munger_inversion_summary}{RESET}\n")

    # Section 3: Masters Boardroom Debate
    print(f"{BOLD}{CYAN}🏛️ Investor Masters Boardroom Debate (6 大师视角对抗):{RESET}")
    print(f"{DIM}─────────────────────────────────────────────────────────────────────────────────────────────{RESET}")
    for v in debate.votes:
        color = GREEN if "BUY" in v.verdict else (RED if "SELL" in v.verdict or "PASS" in v.verdict else YELLOW)
        print(f"  {BOLD}{v.name:<18}{RESET} [{CYAN}{v.role:<30}{RESET}] Score: {YELLOW}{v.score:.1f}{RESET} | Verdict: {color}{v.verdict}{RESET}")
        print(f"    {DIM}Thesis:{RESET} {v.key_thesis}")
        print(f"    {RED}Concern:{RESET} {v.primary_concern}")
    print(f"{DIM}─────────────────────────────────────────────────────────────────────────────────────────────{RESET}\n")

    # Section 4: Moat & Risk Redlines
    print(f"{BOLD}{RED}🛑 Risk Manager Execution Mandate (风控执行红线):{RESET}")
    print(f"  • {BOLD}建议持仓上限:{RESET} {YELLOW}{risk.recommended_max_allocation_pct:.1f}%{RESET} | {BOLD}动态止损线:{RESET} {RED}{risk.stop_loss_trigger_pct:.1f}%{RESET}")
    print(f"  • {BOLD}一票否决/离场触发条件:{RESET}")
    for crit in risk.redline_failure_criteria:
        print(f"    - {crit}")
    print()


def print_comparison_table(reports: List[ComprehensiveAnalysisReport]):
    print(f"\n{BOLD}{CYAN}╔════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║                           🏆 OmniAlpha Cross-Sectional Ranking & Comparison Board                          ║{RESET}")
    print(f"{BOLD}{CYAN}╚════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝{RESET}\n")

    header_fmt = "{:<5} {:<8} {:<24} {:<16} {:<15} {:<12} {:<12} {:<12} {:<10} {:<18}"
    row_fmt    = "{:<5} {:<8} {:<24} {:<16} {:<15} {:<12} {:<12} {:<12} {:<10} {:<18}"

    print(f"{BOLD}" + header_fmt.format(
        "Rank", "Ticker", "Company Name", "Price (P/E)", "Chokepoint", "Masters", "MoS (DCF)", "Qlib Alpha", "Total", "Recommendation"
    ) + f"{RESET}")
    print(f"{DIM}" + "─" * 128 + f"{RESET}")

    for i, r in enumerate(reports, 1):
        medal = "🥇 #1" if i == 1 else ("🥈 #2" if i == 2 else ("🥉 #3" if i == 3 else f"   #{i}"))
        f = r.financials
        c = r.chokepoint
        m = r.masters_debate
        v = r.valuation
        q = r.quant_factors

        color = GREEN if i == 1 else (CYAN if i == 2 else (YELLOW if i == 3 else RED))

        print(row_fmt.format(
            medal,
            f"{BOLD}{f.ticker}{RESET}",
            f.name[:22],
            f"${f.price:.2f} ({f.pe:.1f}x)",
            f"L{c.chokepoint_level} ({c.overall_score})",
            f"{m.consensus_score}/5.0",
            f"{v.margin_of_safety_pct:+.1f}%",
            f"{q.composite_alpha_score}",
            f"{color}{BOLD}{r.final_composite_score}{RESET}",
            f"{color}{r.overall_recommendation.split(' ')[0]}{RESET}"
        ))

    print(f"{DIM}" + "─" * 128 + f"{RESET}\n")


def main():
    parser = argparse.ArgumentParser(
        prog="omni-alpha",
        description="OmniAlpha Agent - Institutional-Grade AI Investment Research Framework."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Deep dive analysis on a single stock ticker")
    analyze_parser.add_argument("ticker", help="Stock ticker symbol (e.g. UBER, TSM, APP, ADBE, SOFI)")

    # compare command
    compare_parser = subparsers.add_parser("compare", help="Cross-sectional comparative ranking of multiple tickers")
    compare_parser.add_argument("tickers", nargs="+", help="List of stock tickers (e.g. SOFI APP UBER ADBE)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    orchestrator = OmniAlphaOrchestrator()

    if args.command == "analyze":
        report = orchestrator.analyze_single(args.ticker)
        print_single_report(report)

    elif args.command == "compare":
        reports = orchestrator.compare_multiple(args.tickers)
        print_comparison_table(reports)


if __name__ == "__main__":
    main()
