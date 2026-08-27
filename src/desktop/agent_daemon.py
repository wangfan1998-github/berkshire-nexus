"""Long-running paper-agent loop managed by the desktop application's process state."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .service import DesktopService, json_safe


def _write(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(json_safe(value), handle, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser(prog="berkshire-nexus-agent-daemon")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--interval-minutes", type=float, default=60.0)
    parser.add_argument("--cash", type=float, default=100_000.0)
    parser.add_argument("--auto-promote-paper", action="store_true")
    parser.add_argument("--risk-config-json", default="{}")
    args = parser.parse_args()

    if args.interval_minutes < 1.0:
        raise SystemExit("interval-minutes must be at least 1")
    service = DesktopService(args.state_dir)
    risk_config = json.loads(args.risk_config_json)
    status_path = args.state_dir / "desktop_agent_status.json"
    cycles_completed = 0
    while True:
        started_at = datetime.now(timezone.utc).isoformat()
        status: Dict[str, Any] = {
            "running": True,
            "state": "running_cycle",
            "pid": os.getpid(),
            "tickers": [value.upper() for value in args.tickers],
            "interval_minutes": args.interval_minutes,
            "cycles_completed": cycles_completed,
            "cycle_started_at_utc": started_at,
            "last_error": None,
        }
        _write(status_path, status)
        try:
            result = service.run_paper_cycle(
                args.tickers,
                initial_cash=args.cash,
                auto_promote_paper=args.auto_promote_paper,
                risk_config=risk_config,
            )
            cycles_completed += 1
            status.update({
                "state": "waiting",
                "cycles_completed": cycles_completed,
                "last_cycle_at_utc": result["cycle"]["generated_at_utc"],
                "last_audit_path": result["cycle"]["audit_path"],
            })
        except Exception as error:
            status.update({
                "state": "error_waiting",
                "last_error": str(error),
            })
        status["next_cycle_at_epoch"] = time.time() + args.interval_minutes * 60.0
        _write(status_path, status)
        time.sleep(args.interval_minutes * 60.0)


if __name__ == "__main__":
    main()
