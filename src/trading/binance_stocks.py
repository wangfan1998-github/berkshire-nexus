"""Direct Binance Stocks SAPI adapter.

The adapter is intentionally isolated from strategy code. Read-only preflight and
account inspection are available with an API key, while order placement requires
both an explicit constructor flag and a process-level acknowledgement.

Endpoint paths below were verified to exist against ``api.binance.com`` (an
unauthenticated probe returns ``-2014 API-key format invalid`` for a live route
and ``404`` for a non-existent one). Response *field* names are not fully
documented, so every reader in this module parses defensively across the field
spellings Binance uses elsewhere and always keeps the raw payload.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .types import OrderIntent


LIVE_ACKNOWLEDGEMENT = "I_ACKNOWLEDGE_REAL_MONEY"

# Assets which represent settlement cash rather than an equity position.
CASH_ASSETS: Set[str] = {"USDC", "USDT", "USD", "FDUSD", "BUSD"}

# Binance rate-limits /order/place at 200 req/min per UID; back off politely.
_RETRY_STATUS = {418, 429, 500, 502, 503, 504}


class BinanceAPIError(RuntimeError):
    def __init__(self, code: object, message: str, status: Optional[int] = None):
        super().__init__(f"Binance API error {code}: {message}")
        self.code = code
        self.message = message
        self.status = status


class LiveTradingDisabledError(RuntimeError):
    pass


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _first(payload: Dict[str, Any], *names: str, default: Any = None) -> Any:
    """Return the first present key from ``names``.

    Binance is inconsistent between products (``orderId`` vs ``order_id``,
    ``executedQty`` vs ``filledQuantity``), and the Stocks response schemas are
    not published, so readers accept every plausible spelling.
    """

    for name in names:
        if name in payload and payload[name] not in (None, ""):
            return payload[name]
    return default


def _rows(payload: Any, *keys: str) -> List[Dict[str, Any]]:
    """Normalise Binance list responses that may be bare or envelope-wrapped."""

    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        for value in payload.values():
            if isinstance(value, list) and all(isinstance(row, dict) for row in value):
                return list(value)
    return []


class BinanceStocksClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str = "",
        *,
        base_url: str = "https://api.binance.com",
        recv_window: int = 5_000,
        allow_live_orders: bool = False,
        timeout: int = 10,
        max_retries: int = 2,
        send_tokenize_flag: bool = True,
    ):
        if not api_key:
            raise ValueError("Binance API key is required")
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.recv_window = recv_window
        self.allow_live_orders = allow_live_orders
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        # `tokenize` is present in the original adapter but absent from the
        # published parameter list. Keep it switchable so a rejection can be
        # resolved without a code change.
        self.send_tokenize_flag = send_tokenize_flag

    @staticmethod
    def sign_query(params: Dict[str, object], secret: str) -> str:
        encoded = urllib.parse.urlencode(params)
        return hmac.new(secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()

    @property
    def has_secret(self) -> bool:
        return bool(self.api_secret)

    # ------------------------------------------------------------------
    # Market data (API key only, no signature)
    # ------------------------------------------------------------------

    def exchange_info(self, symbol: Optional[str] = None) -> Dict[str, object]:
        params: Dict[str, object] = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request("GET", "/sapi/v1/equity/market/exchangeInfo", params=params)

    def latest_quote(self, symbol: str) -> Dict[str, object]:
        return self._request(
            "GET",
            "/sapi/v1/equity/market/quote",
            params={"symbol": symbol.upper()},
        )

    def tokenized_assets(self) -> Dict[str, object]:
        return self._request("GET", "/sapi/v1/equity/market/tokenized-assets")

    def preflight(self, symbols: Iterable[str]) -> Dict[str, object]:
        result: Dict[str, object] = {"exchange_info": {}, "quotes": {}}
        for symbol in symbols:
            ticker = symbol.upper()
            result["exchange_info"][ticker] = self.exchange_info(ticker)
            result["quotes"][ticker] = self.latest_quote(ticker)
        return result

    def tradable_symbols(self) -> Dict[str, Dict[str, Any]]:
        """Map ticker -> exchangeInfo row for the whole equity universe."""

        payload = self.exchange_info()
        universe: Dict[str, Dict[str, Any]] = {}
        for row in _rows(payload, "symbols", "data"):
            symbol = str(_first(row, "symbol", "ticker", default="")).upper()
            if symbol:
                universe[symbol] = row
        return universe

    # ------------------------------------------------------------------
    # Account (signed, read-only)
    # ------------------------------------------------------------------

    def accept_disclaimer(self) -> Dict[str, object]:
        """Sign the US-equity disclaimer.

        Orders placed before this returns successfully are rejected by Binance
        with ``486410``.
        """

        return self._request("POST", "/sapi/v1/equity/account/disclaimer", signed=True)

    def funding_assets(self, asset: Optional[str] = None) -> List[Dict[str, Any]]:
        """CARD wallet balances - the default settlement wallet for equities."""

        params: Dict[str, object] = {}
        if asset:
            params["asset"] = asset.upper()
        payload = self._request(
            "POST", "/sapi/v1/asset/get-funding-asset", params=params, signed=True
        )
        return _rows(payload, "data", "assets")

    def spot_assets(self) -> List[Dict[str, Any]]:
        """MAIN (spot) wallet balances, used when orders specify walletType=MAIN."""

        payload = self._request(
            "POST", "/sapi/v3/asset/getUserAsset", params={"needBtcValuation": "false"}, signed=True
        )
        return _rows(payload, "data", "assets")

    def open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, object] = {}
        if symbol:
            params["symbol"] = symbol.upper()
        payload = self._request(
            "GET", "/sapi/v1/equity/order/open-orders", params=params, signed=True
        )
        return _rows(payload, "orders", "data", "rows")

    def order_history(
        self,
        *,
        symbol: Optional[str] = None,
        order_status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, object] = {"limit": max(1, min(int(limit), 500))}
        if symbol:
            params["symbol"] = symbol.upper()
        if order_status:
            # Terminal states only; NEW/ACCEPTED are rejected as filters.
            params["orderStatus"] = order_status.upper()
        payload = self._request("GET", "/sapi/v1/equity/order/history", params=params, signed=True)
        return _rows(payload, "orders", "data", "rows")

    def trade_history(
        self,
        *,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, object] = {"limit": max(1, min(int(limit), 500))}
        if symbol:
            params["symbol"] = symbol.upper()
        payload = self._request("GET", "/sapi/v1/equity/trade/history", params=params, signed=True)
        return _rows(payload, "trades", "data", "rows")

    def account_snapshot(self, *, include_spot: bool = True) -> Dict[str, Any]:
        """Authoritative cash + equity holdings from Binance.

        Binance publishes no ``/equity/account`` position endpoint: filled stock
        quantities land in the wallet as ordinary assets (``CARD`` by default,
        ``MAIN`` when the order set ``walletType=MAIN``). Positions are therefore
        reconstructed by intersecting wallet balances with the tradable equity
        universe, which keeps mints, transfers and corporate actions correct in a
        way that summing trade history never would.
        """

        if not self.has_secret:
            raise ValueError("Binance API secret is required to read account balances")

        try:
            universe = set(self.tradable_symbols())
        except BinanceAPIError:
            universe = set()

        wallets: Dict[str, List[Dict[str, Any]]] = {"CARD": [], "MAIN": []}
        errors: Dict[str, str] = {}
        try:
            wallets["CARD"] = self.funding_assets()
        except (BinanceAPIError, ValueError) as error:
            errors["CARD"] = str(error)
        if include_spot:
            try:
                wallets["MAIN"] = self.spot_assets()
            except (BinanceAPIError, ValueError) as error:
                errors["MAIN"] = str(error)

        positions: Dict[str, Dict[str, Any]] = {}
        cash_by_asset: Dict[str, float] = {}
        unclassified: List[Dict[str, Any]] = []

        for wallet, rows in wallets.items():
            for row in rows:
                asset = str(_first(row, "asset", "coin", "symbol", default="")).upper()
                if not asset:
                    continue
                free = _as_float(_first(row, "free", "available", "freeAmount"))
                locked = _as_float(_first(row, "locked", "freeze", "frozen")) + _as_float(
                    _first(row, "withdrawing")
                )
                total = free + locked
                if total <= 0.0:
                    continue
                if asset in CASH_ASSETS:
                    cash_by_asset[asset] = cash_by_asset.get(asset, 0.0) + total
                    continue
                if universe and asset not in universe:
                    unclassified.append({"asset": asset, "wallet": wallet, "total": total})
                    continue
                entry = positions.setdefault(
                    asset,
                    {"ticker": asset, "quantity": 0.0, "free": 0.0, "locked": 0.0, "wallets": []},
                )
                entry["quantity"] += total
                entry["free"] += free
                entry["locked"] += locked
                if wallet not in entry["wallets"]:
                    entry["wallets"].append(wallet)

        return {
            "cash_by_asset": cash_by_asset,
            "cash": sum(cash_by_asset.values()),
            "positions": sorted(positions.values(), key=lambda item: item["ticker"]),
            "unclassified_assets": unclassified,
            "equity_universe_size": len(universe),
            "wallet_errors": errors,
        }

    # ------------------------------------------------------------------
    # Trading (signed, gated)
    # ------------------------------------------------------------------

    def place_order(self, order: OrderIntent) -> Dict[str, object]:
        self._assert_live_enabled()
        if not self.api_secret:
            raise ValueError("Binance API secret is required for signed trade endpoints")
        if order.tokenize:
            raise ValueError("BerkshireNexus live adapter only permits direct equities (tokenize=False)")

        params: Dict[str, object] = {
            "symbol": order.ticker.upper(),
            "side": order.side,
            "orderType": order.order_type,
            "clientOrderId": order.client_order_id,
        }
        if self.send_tokenize_flag:
            params["tokenize"] = "false"
        if order.order_type == "LIMIT":
            if order.limit_price is None:
                raise ValueError("limit_price is required for LIMIT orders")
            params.update({
                "price": f"{order.limit_price:.2f}",
                "quantity": self._decimal(order.quantity),
                "timeInForce": order.time_in_force,
                # tradingSession is mandatory for LIMIT and must be absent for MARKET.
                "tradingSession": order.trading_session,
            })
        elif order.order_type == "MARKET" and order.side == "BUY":
            params["notional"] = self._decimal(order.notional)
        elif order.order_type == "MARKET" and order.side == "SELL":
            params["quantity"] = self._decimal(order.quantity)
        else:
            raise ValueError("unsupported stock order field combination")
        return self._request("POST", "/sapi/v1/equity/order/place", params=params, signed=True)

    def order_detail(
        self,
        *,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, object]:
        if not order_id and not client_order_id:
            raise ValueError("order_id or client_order_id is required")
        params: Dict[str, object] = {}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["clientOrderId"] = client_order_id
        return self._request("GET", "/sapi/v1/equity/order/detail", params=params, signed=True)

    def cancel_order(self, order_id: str) -> Dict[str, object]:
        self._assert_live_enabled()
        return self._request(
            "POST",
            "/sapi/v1/equity/order/cancel",
            params={"orderId": order_id},
            signed=True,
        )

    def cancel_all(self, symbol: Optional[str] = None) -> Dict[str, object]:
        self._assert_live_enabled()
        params: Dict[str, object] = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request(
            "POST", "/sapi/v1/equity/order/cancel-all", params=params, signed=True
        )

    def _assert_live_enabled(self) -> None:
        environment_ack = os.environ.get("BERKSHIRE_NEXUS_LIVE_TRADING", "")
        if not self.allow_live_orders or environment_ack != LIVE_ACKNOWLEDGEMENT:
            raise LiveTradingDisabledError(
                "live orders require allow_live_orders=True and "
                f"BERKSHIRE_NEXUS_LIVE_TRADING={LIVE_ACKNOWLEDGEMENT}"
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, object]] = None,
        signed: bool = False,
    ) -> Dict[str, object]:
        attempt = 0
        while True:
            request_params: Dict[str, object] = dict(params or {})
            if signed:
                if not self.api_secret:
                    raise ValueError("Binance API secret is required for signed endpoints")
                request_params["recvWindow"] = self.recv_window
                # Signed retries must re-stamp timestamp and re-sign.
                request_params["timestamp"] = int(time.time() * 1000)
                request_params["signature"] = self.sign_query(request_params, self.api_secret)
            query = urllib.parse.urlencode(request_params)
            url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
            request = urllib.request.Request(
                url,
                method=method,
                headers={"X-MBX-APIKEY": self.api_key, "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as error:
                raw = error.read().decode("utf-8", errors="replace")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {"code": error.code, "msg": raw or error.reason}
                # Never retry a rejected order: a timeout-free 4xx is deterministic.
                if error.code in _RETRY_STATUS and attempt < self.max_retries:
                    attempt += 1
                    time.sleep(min(2.0 ** attempt, 4.0))
                    continue
                raise BinanceAPIError(
                    payload.get("code"), str(payload.get("msg", payload)), error.code
                ) from error
            except (urllib.error.URLError, TimeoutError) as error:
                # A network failure on a POST is ambiguous - the order may have
                # landed. Only idempotent reads are retried.
                if method == "GET" and attempt < self.max_retries:
                    attempt += 1
                    time.sleep(min(2.0 ** attempt, 4.0))
                    continue
                raise BinanceAPIError("network", str(error), None) from error

    @staticmethod
    def _decimal(value: float) -> str:
        return f"{value:.8f}".rstrip("0").rstrip(".")

    # ------------------------------------------------------------------
    # Normalisation helpers shared with the live broker
    # ------------------------------------------------------------------

    @staticmethod
    def normalise_order(row: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten a Binance order row into the fields the app relies on."""

        filled = _as_float(
            _first(row, "executedQty", "filledQuantity", "executedQuantity", "filledQty")
        )
        quantity = _as_float(_first(row, "origQty", "quantity", "orderQuantity"))
        average = _as_float(_first(row, "avgPrice", "averagePrice", "avgFillPrice"))
        if average <= 0.0:
            quote_qty = _as_float(_first(row, "cummulativeQuoteQty", "executedQuoteQty", "quoteQty"))
            if quote_qty > 0.0 and filled > 0.0:
                average = quote_qty / filled
        return {
            "order_id": str(_first(row, "orderId", "order_id", "id", default="")),
            "client_order_id": str(_first(row, "clientOrderId", "client_order_id", default="")),
            "ticker": str(_first(row, "symbol", "ticker", default="")).upper(),
            "side": str(_first(row, "side", default="")).upper(),
            "order_type": str(_first(row, "orderType", "type", default="")).upper(),
            "status": str(_first(row, "status", "orderStatus", default="")).upper(),
            "quantity": quantity,
            "filled_quantity": filled,
            "average_price": average,
            "limit_price": _as_float(_first(row, "price", "limitPrice")),
            "fee": _as_float(_first(row, "fee", "commission", "feeAmount")),
            "session": str(_first(row, "session", "tradingSession", default="")).upper(),
            "updated_at": _first(row, "updateTime", "time", "transactTime", "createTime"),
            "raw": row,
        }

    @staticmethod
    def is_terminal_status(status: str) -> bool:
        return status.upper() in {"FILLED", "CANCELED", "CANCELLED", "EXPIRED", "REJECTED"}


def classify_place_ack(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Interpret a /order/place acknowledgement.

    ``status`` on place/cancel is an ack code (``S`` accepted / ``F`` failed),
    never an order lifecycle state - treating ``S`` as "filled" would be wrong.
    """

    ack = str(_first(payload, "status", default="")).upper()
    return {
        "accepted": ack == "S",
        "ack": ack,
        "order_id": str(_first(payload, "orderId", "order_id", default="")),
        "client_order_id": str(_first(payload, "clientOrderId", "client_order_id", default="")),
        "raw": payload,
    }


def summarise_symbol_tradability(row: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the gate fields the live broker checks before submitting."""

    tradability = str(_first(row, "tradability", default="")).upper()
    return {
        "tradability": tradability,
        "allows_buy": tradability in {"BUY_SELL", "BUY"},
        "allows_sell": tradability in {"BUY_SELL", "SELL"},
        "halted": tradability == "NONE",
    }


def merge_quote_price(quote: Dict[str, Any]) -> float:
    """Best-effort last price from an equity quote payload."""

    if not isinstance(quote, dict):
        return 0.0
    candidates: Sequence[str] = (
        "price", "lastPrice", "last", "close", "markPrice", "midPrice",
    )
    direct = _as_float(_first(quote, *candidates))
    if direct > 0.0:
        return direct
    for row in _rows(quote, "data", "quotes", "symbols"):
        nested = _as_float(_first(row, *candidates))
        if nested > 0.0:
            return nested
    bid = _as_float(_first(quote, "bidPrice", "bid"))
    ask = _as_float(_first(quote, "askPrice", "ask"))
    if bid > 0.0 and ask > 0.0:
        return (bid + ask) / 2.0
    return 0.0
