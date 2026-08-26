"""Direct Binance Stocks SAPI adapter.

The adapter is intentionally isolated from strategy code. Read-only preflight is
available with an API key, while order placement requires both an explicit
constructor flag and a process-level acknowledgement.
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
from typing import Dict, Iterable, Optional

from .types import OrderIntent


LIVE_ACKNOWLEDGEMENT = "I_ACKNOWLEDGE_REAL_MONEY"


class BinanceAPIError(RuntimeError):
    def __init__(self, code: object, message: str, status: Optional[int] = None):
        super().__init__(f"Binance API error {code}: {message}")
        self.code = code
        self.message = message
        self.status = status


class LiveTradingDisabledError(RuntimeError):
    pass


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
    ):
        if not api_key:
            raise ValueError("Binance API key is required")
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.recv_window = recv_window
        self.allow_live_orders = allow_live_orders
        self.timeout = timeout

    @staticmethod
    def sign_query(params: Dict[str, object], secret: str) -> str:
        encoded = urllib.parse.urlencode(params)
        return hmac.new(secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()

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

    def preflight(self, symbols: Iterable[str]) -> Dict[str, object]:
        result: Dict[str, object] = {"exchange_info": {}, "quotes": {}}
        for symbol in symbols:
            ticker = symbol.upper()
            result["exchange_info"][ticker] = self.exchange_info(ticker)
            result["quotes"][ticker] = self.latest_quote(ticker)
        return result

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
            "tokenize": "false",
        }
        if order.order_type == "LIMIT":
            if order.limit_price is None:
                raise ValueError("limit_price is required for LIMIT orders")
            params.update({
                "price": f"{order.limit_price:.2f}",
                "quantity": self._decimal(order.quantity),
                "timeInForce": order.time_in_force,
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
        request_params: Dict[str, object] = dict(params or {})
        if signed:
            if not self.api_secret:
                raise ValueError("Binance API secret is required for signed endpoints")
            request_params["recvWindow"] = self.recv_window
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
            raise BinanceAPIError(payload.get("code"), str(payload.get("msg", payload)), error.code) from error

    @staticmethod
    def _decimal(value: float) -> str:
        return f"{value:.8f}".rstrip("0").rstrip(".")
