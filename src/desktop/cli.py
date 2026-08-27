"""Strict JSON command surface for the desktop application's Rust bridge."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .service import DesktopService, json_safe


def _emit(value: Any) -> None:
    print(json.dumps(json_safe(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False))


def main() -> None:
    parser = argparse.ArgumentParser(prog="berkshire-nexus-desktop")
    parser.add_argument("--state-dir", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("snapshot")

    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("tickers", nargs="+")
    analyze.add_argument("--research-config-json", default="{}")

    cycle = subparsers.add_parser("cycle")
    cycle.add_argument("tickers", nargs="+")
    cycle.add_argument("--cash", type=float, default=100_000.0)
    cycle.add_argument("--auto-promote-paper", action="store_true")
    cycle.add_argument("--risk-config-json", default="{}")
    cycle.add_argument("--research-config-json", default="{}")

    subparsers.add_parser("model-promote")

    test_ai = subparsers.add_parser("test-ai")
    test_ai.add_argument("--research-config-json", required=True)

    preflight = subparsers.add_parser("binance-preflight")
    preflight.add_argument("tickers", nargs="+")

    subparsers.add_parser("live-account")
    subparsers.add_parser("live-reconcile")
    subparsers.add_parser("live-accept-disclaimer")

    cancel_all = subparsers.add_parser("live-cancel-all")
    cancel_all.add_argument("--symbol", default="")

    live_cycle = subparsers.add_parser("live-cycle")
    live_cycle.add_argument("tickers", nargs="+")
    live_cycle.add_argument("--risk-config-json", default="{}")
    live_cycle.add_argument("--research-config-json", default="{}")
    # Submission requires the explicit acknowledgement AND --submit. Preview is
    # the default so a mistaken invocation can never reach the market.
    live_cycle.add_argument("--confirmation", default="")
    live_cycle.add_argument("--submit", action="store_true")

    args = parser.parse_args()
    service = DesktopService(args.state_dir)
    binance_key = os.environ.get("BINANCE_API_KEY", "")
    binance_secret = os.environ.get("BINANCE_API_SECRET", "")
    try:
        if args.command == "snapshot":
            value = service.snapshot()
        elif args.command == "analyze":
            value = service.analyze(
                args.tickers,
                research_config=json.loads(args.research_config_json),
                ai_api_key=os.environ.get("BERKSHIRE_NEXUS_AI_API_KEY", ""),
            )
        elif args.command == "cycle":
            value = service.run_paper_cycle(
                args.tickers,
                initial_cash=args.cash,
                auto_promote_paper=args.auto_promote_paper,
                risk_config=json.loads(args.risk_config_json),
                research_config=json.loads(args.research_config_json),
                ai_api_key=os.environ.get("BERKSHIRE_NEXUS_AI_API_KEY", ""),
            )
        elif args.command == "model-promote":
            value = service.promote_model()
        elif args.command == "binance-preflight":
            value = service.binance_preflight(
                binance_key,
                args.tickers,
            )
        elif args.command == "live-account":
            value = service.live_account(binance_key, binance_secret)
        elif args.command == "live-reconcile":
            value = service.live_reconcile(binance_key, binance_secret)
        elif args.command == "live-accept-disclaimer":
            value = service.live_accept_disclaimer(binance_key, binance_secret)
        elif args.command == "live-cancel-all":
            value = service.live_cancel_all(
                binance_key,
                binance_secret,
                args.symbol or None,
            )
        elif args.command == "live-cycle":
            value = service.run_live_cycle(
                args.tickers,
                api_key=binance_key,
                api_secret=binance_secret,
                research_config=json.loads(args.research_config_json),
                ai_api_key=os.environ.get("BERKSHIRE_NEXUS_AI_API_KEY", ""),
                risk_config=json.loads(args.risk_config_json),
                confirmation=args.confirmation,
                dry_run=not args.submit,
            )
        elif args.command == "test-ai":
            value = service.test_ai_provider(
                json.loads(args.research_config_json),
                os.environ.get("BERKSHIRE_NEXUS_AI_API_KEY", ""),
            )
        else:
            raise ValueError(f"unsupported desktop command: {args.command}")
        _emit(value)
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
