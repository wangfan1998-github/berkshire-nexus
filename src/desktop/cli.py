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

    cycle = subparsers.add_parser("cycle")
    cycle.add_argument("tickers", nargs="+")
    cycle.add_argument("--cash", type=float, default=100_000.0)
    cycle.add_argument("--auto-promote-paper", action="store_true")
    cycle.add_argument("--risk-config-json", default="{}")

    subparsers.add_parser("model-promote")

    preflight = subparsers.add_parser("binance-preflight")
    preflight.add_argument("tickers", nargs="+")

    args = parser.parse_args()
    service = DesktopService(args.state_dir)
    try:
        if args.command == "snapshot":
            value = service.snapshot()
        elif args.command == "analyze":
            value = service.analyze(args.tickers)
        elif args.command == "cycle":
            value = service.run_paper_cycle(
                args.tickers,
                initial_cash=args.cash,
                auto_promote_paper=args.auto_promote_paper,
                risk_config=json.loads(args.risk_config_json),
            )
        elif args.command == "model-promote":
            value = service.promote_model()
        elif args.command == "binance-preflight":
            value = service.binance_preflight(
                os.environ.get("BINANCE_API_KEY", ""),
                args.tickers,
            )
        else:
            raise ValueError(f"unsupported desktop command: {args.command}")
        _emit(value)
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
