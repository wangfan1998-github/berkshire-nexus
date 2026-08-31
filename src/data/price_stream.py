"""Binance equity real-time price stream.

The REST quote endpoint (``/sapi/v1/equity/market/quote``) returns only
``bidPrice``/``askPrice`` — there is no last-traded price anywhere in the equity
REST API (``/market/kline``, ``/market/ticker``, ``/market/trades`` and
``/market/depth`` all return 404). Deriving a price from the book therefore
produced an estimate that drifted badly on thin pre-market books: SMH quoted
570.11/599.99, a 5.1% spread whose midpoint read 585 while the Binance app itself
showed 566.74.

The real price is published over WebSocket instead. ``wss://nbstream.binance.com
/equity/ws/price`` streams every symbol continuously; measured against the app,
the ``p`` field matched to within a few cents (566.86 vs 566.74).

Implemented on the standard library so the project keeps its zero-dependency
runtime: a minimal client-side WebSocket handshake and frame reader, used for a
single short-lived snapshot rather than a persistent subscription.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

STREAM_HOST = "nbstream.binance.com"
STREAM_PATH = "/equity/ws/price"

# Market phase reported by the stream's `mp` field.
PHASE_LABELS = {
    "PRE": "盘前",
    "RTH": "盘中",
    "POST": "盘后",
    "CLOSED": "休市",
    "OVERNIGHT": "夜盘",
}


@dataclass
class StreamPrice:
    ticker: str
    price: float = 0.0
    # Fields observed on the wire, kept under readable names.
    previous_close: float = 0.0     # pc
    today_close: float = 0.0        # tc
    last_regular_close: float = 0.0 # lrc
    prior_regular_close: float = 0.0 # prc
    phase: str = ""                 # mp
    updated_at_ms: int = 0          # t

    @property
    def phase_label(self) -> str:
        return PHASE_LABELS.get(self.phase.upper(), self.phase)

    @property
    def change_pct(self) -> float:
        """Move versus the previous close, which is what a quote screen shows."""

        base = self.previous_close or self.last_regular_close
        if base <= 0.0 or self.price <= 0.0:
            return 0.0
        return (self.price / base - 1.0) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["phase_label"] = self.phase_label
        value["change_pct"] = round(self.change_pct, 4)
        return value


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class EquityPriceStream:
    """One-shot snapshot of the all-symbols price stream.

    Not a long-lived subscription: the briefing needs a consistent set of prices
    at a point in time, and holding a socket open across a multi-minute run would
    add reconnect handling for no benefit.
    """

    def __init__(self, timeout: float = 12.0, host: str = STREAM_HOST, path: str = STREAM_PATH):
        self.timeout = timeout
        self.host = host
        self.path = path

    def snapshot(
        self,
        tickers: Optional[Iterable[str]] = None,
        *,
        max_seconds: float = 10.0,
    ) -> Dict[str, StreamPrice]:
        """Collect prices until every requested ticker is seen or time runs out.

        The stream pushes symbols in rotating batches, so a thinly traded name can
        take several messages to appear. Returning early once the wanted set is
        complete keeps the common case fast.
        """

        wanted: Optional[Set[str]] = (
            {str(value).upper().strip() for value in tickers if str(value).strip()}
            if tickers is not None else None
        )
        found: Dict[str, StreamPrice] = {}
        deadline = time.monotonic() + max_seconds

        sock = None
        try:
            sock = self._connect()
            buffer = b""
            while time.monotonic() < deadline:
                if wanted is not None and wanted.issubset(found.keys()):
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                sock.settimeout(min(remaining, 3.0))
                try:
                    chunk = sock.recv(65536)
                except (socket.timeout, ssl.SSLWantReadError):
                    continue
                if not chunk:
                    break
                buffer += chunk
                payloads, buffer = self._drain(buffer)
                for payload in payloads:
                    self._absorb(payload, wanted, found)
        except (OSError, ssl.SSLError, ValueError):
            # A stream failure must not break the caller; they fall back to REST.
            pass
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        return found

    # ------------------------------------------------------------------

    def _connect(self):
        key = base64.b64encode(os.urandom(16)).decode()
        raw = socket.create_connection((self.host, 443), timeout=self.timeout)
        sock = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host)
        sock.send((
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode())
        header = b""
        sock.settimeout(self.timeout)
        while b"\r\n\r\n" not in header:
            byte = sock.recv(1)
            if not byte:
                raise ValueError("stream closed during handshake")
            header += byte
        status = header.split(b"\r\n", 1)[0]
        if b"101" not in status:
            raise ValueError(f"websocket handshake rejected: {status!r}")
        return sock

    @staticmethod
    def _drain(buffer: bytes):
        """Pull complete text frames out of the buffer.

        Server frames are unmasked; control frames are skipped. Fragmentation is
        not handled because this stream sends each JSON payload as one frame.
        """

        payloads: List[str] = []
        while len(buffer) >= 2:
            first, second = buffer[0], buffer[1]
            length = second & 0x7F
            offset = 2
            if length == 126:
                if len(buffer) < 4:
                    break
                length = struct.unpack(">H", buffer[2:4])[0]
                offset = 4
            elif length == 127:
                if len(buffer) < 10:
                    break
                length = struct.unpack(">Q", buffer[2:10])[0]
                offset = 10
            if len(buffer) < offset + length:
                break
            frame = buffer[offset:offset + length]
            buffer = buffer[offset + length:]
            if (first & 0x0F) == 0x1:  # text
                payloads.append(frame.decode("utf-8", errors="replace"))
        return payloads, buffer

    def refresh_cache(
        self,
        cache_path: Path,
        *,
        max_seconds: float = 25.0,
        stale_after_seconds: float = 900.0,
    ) -> Dict[str, StreamPrice]:
        """Merge a fresh snapshot into a persisted cache and return the union.

        The stream rotates through thousands of symbols, so waiting for a
        specific set takes minutes — measured 5 of 11 holdings in 40s. Blocking a
        request on that is unacceptable, but the prices are still the only real
        traded prices Binance exposes. So each run harvests whatever arrives
        within a short window and merges it with what earlier runs saw; entries
        older than ``stale_after_seconds`` are dropped rather than served as
        current.
        """

        merged: Dict[str, StreamPrice] = {}
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - int(stale_after_seconds * 1000)

        try:
            if cache_path.exists():
                with cache_path.open("r", encoding="utf-8") as handle:
                    for ticker, row in dict(json.load(handle)).items():
                        stamp = int(_as_float(row.get("updated_at_ms")))
                        if stamp >= cutoff:
                            merged[str(ticker).upper()] = StreamPrice(
                                ticker=str(ticker).upper(),
                                price=_as_float(row.get("price")),
                                previous_close=_as_float(row.get("previous_close")),
                                today_close=_as_float(row.get("today_close")),
                                last_regular_close=_as_float(row.get("last_regular_close")),
                                prior_regular_close=_as_float(row.get("prior_regular_close")),
                                phase=str(row.get("phase") or ""),
                                updated_at_ms=stamp,
                            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            merged = {}

        # No ticker filter: take everything the stream offers in the window, so
        # later runs benefit from symbols this one happened to catch.
        merged.update(self.snapshot(None, max_seconds=max_seconds))

        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(
                    {k: v.to_dict() for k, v in merged.items()},
                    handle, ensure_ascii=False,
                )
            os.replace(temporary, cache_path)
        except OSError:
            pass
        return merged

    @staticmethod
    def _absorb(payload: str, wanted: Optional[Set[str]], found: Dict[str, StreamPrice]) -> None:
        try:
            message = json.loads(payload)
        except json.JSONDecodeError:
            return
        for row in message.get("rates") or []:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("s") or "").upper()
            if not ticker or (wanted is not None and ticker not in wanted):
                continue
            price = _as_float(row.get("p"))
            if price <= 0.0:
                continue
            # Later messages are fresher; overwrite rather than keep the first.
            found[ticker] = StreamPrice(
                ticker=ticker,
                price=price,
                previous_close=_as_float(row.get("pc")),
                today_close=_as_float(row.get("tc")),
                last_regular_close=_as_float(row.get("lrc")),
                prior_regular_close=_as_float(row.get("prc")),
                phase=str(row.get("mp") or ""),
                updated_at_ms=int(_as_float(row.get("t"))),
            )
