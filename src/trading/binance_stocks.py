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
CASH_ASSETS: Set[str] = {"USDC", "USDT", "USD", "FDUSD", "BUSD", "USD1"}

# Wallet balances namespace equity holdings with this prefix (``EQ_AVGO``),
# while /equity/market/exchangeInfo returns the bare ticker (``AVGO``).
# Verified against a live account: without stripping it, every real stock
# position fails the universe check and is silently discarded.
EQUITY_ASSET_PREFIX = "EQ_"


def strip_equity_prefix(asset: str) -> str:
    """Map a wallet asset name onto its exchangeInfo ticker."""

    value = asset.upper()
    if value.startswith(EQUITY_ASSET_PREFIX):
        return value[len(EQUITY_ASSET_PREFIX):]
    return value


def classify_wallet_asset(
    asset: str,
    resolution: Optional[Dict[str, Dict[str, Any]]] = None,
    universe: Optional[Set[str]] = None,
    row: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve a wallet asset to an equity ticker, or None if it is not equity.

    Only positive evidence from Binance counts:

    1. ``stockTicker`` on the wallet row. Equity rows carry it (``EQ_AVGO`` ->
       ``AVGO``); crypto rows return ``stockTicker: null``.
    2. ``EQ_`` prefix — the direct-equity naming convention, trusted alone so
       holdings survive an API outage.
    3. ``/equity/market/tokenized-assets`` mapping, which also supplies the
       multiplier converting a token balance into shares.

    A bare ticker matching the equity universe is deliberately NOT accepted.
    Binance lists ~7,900 equity symbols, and single-letter/short crypto tokens
    collide with them: the token ``U`` (~$1) collides with Unity (~$44), so a
    universe match mispriced a crypto balance 44x. Ambiguous assets are reported
    as unclassified instead.
    """

    value = asset.upper()
    resolution = resolution or {}
    universe = universe or set()

    # Strongest evidence: the wallet row itself names the underlying ticker.
    declared = str((row or {}).get("stockTicker") or "").upper() if row else ""
    if declared:
        return {
            "ticker": declared,
            "multiplier": 1.0,
            "multiplier_valid": True,
            "tokenized": False,
            "resolved_by": "wallet-stockTicker",
        }

    if value.startswith(EQUITY_ASSET_PREFIX):
        return {
            "ticker": value[len(EQUITY_ASSET_PREFIX):],
            "multiplier": 1.0,
            "multiplier_valid": True,
            "tokenized": False,
            "resolved_by": "eq-prefix",
        }

    mapped = resolution.get(value)
    if mapped:
        return {
            "ticker": mapped["ticker"],
            "multiplier": mapped.get("multiplier", 1.0),
            "multiplier_valid": mapped.get("multiplier_valid", True),
            "tokenized": True,
            "resolved_by": "tokenized-assets",
        }

    return None

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


def _earn_flexible_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a Simple Earn flexible position.

    Binance returns two different rates and they are not interchangeable:

    * ``tierAnnualPercentageRate`` — the tiered/promotional rate, keyed by
      balance band (``{"0-200USDC": "0.05"}``). This is what the Binance app
      advertises for the product.
    * ``latestAnnualPercentageRate`` — the realised rate on the *whole* balance,
      which is lower once a holding exceeds the bonus tier.

    Both are reported: ``apr`` follows the platform's headline figure so the
    numbers reconcile with what the user sees, while ``realised_apr`` keeps the
    blended rate actually being earned.
    """

    tiers_raw = row.get("tierAnnualPercentageRate")
    tiers: Dict[str, float] = {}
    if isinstance(tiers_raw, dict):
        tiers = {str(k): _as_float(v) for k, v in tiers_raw.items()}
    realised = _as_float(_first(row, "latestAnnualPercentageRate"))
    # Highest tier is the advertised headline rate for the product.
    headline = max(tiers.values()) if tiers else realised
    return {
        "asset": str(_first(row, "asset", default="")).upper(),
        "amount": _as_float(_first(row, "totalAmount", "amount")),
        "apr": headline,
        "realised_apr": realised,
        "apr_tiers": tiers,
        "cumulative_rewards": _as_float(_first(row, "cumulativeTotalRewards")),
        "yesterday_rewards": _as_float(_first(row, "yesterdayRealTimeRewards")),
        "can_redeem": bool(_first(row, "canRedeem", default=True)),
        "product_id": str(_first(row, "productId", default="")),
    }


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

    def tokenized_assets(self) -> List[Dict[str, Any]]:
        """Authoritative wallet-asset -> underlying-equity mapping.

        Rows look like ``{"assetCode": "AAPLB", "underlyingEquitySymbol": "AAPL",
        "multiplier": "1.00060391"}``. This is the only published way to resolve
        a tokenized wallet balance to a ticker and to a share count, so it is
        preferred over any naming heuristic.
        """

        payload = self._request("GET", "/sapi/v1/equity/market/tokenized-assets")
        return _rows(payload, "data", "assets", "tokenizedAssets")

    def asset_resolution_map(self) -> Dict[str, Dict[str, Any]]:
        """Build wallet-asset -> {ticker, multiplier, tokenized} from the API.

        Falls back to an empty map when the endpoint is unavailable; callers then
        rely on the ``EQ_`` prefix convention alone.
        """

        resolution: Dict[str, Dict[str, Any]] = {}
        try:
            rows = self.tokenized_assets()
        except (BinanceAPIError, ValueError):
            return resolution
        for row in rows:
            code = str(_first(row, "assetCode", "asset", default="")).upper()
            ticker = str(
                _first(row, "underlyingEquitySymbol", "underlyingSymbol", "symbol", default="")
            ).upper()
            if not code or not ticker:
                continue
            multiplier = _as_float(_first(row, "multiplier"), 1.0)
            # A stale or invalid multiplier must not silently scale a position.
            valid = bool(_first(row, "multiplierValid", default=True))
            resolution[code] = {
                "ticker": ticker,
                "multiplier": multiplier if (valid and multiplier > 0.0) else 1.0,
                "multiplier_valid": valid,
                "tokenized": True,
                "name": str(_first(row, "assetName", default="")),
            }
        return resolution

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

    def wallet_balances(self) -> List[Dict[str, Any]]:
        """Per-wallet totals across Spot, Funding, Margin, Futures, Earn, etc.

        Used to detect value the position readers do not cover, so the UI can
        say "money exists elsewhere" instead of silently understating net worth.
        """

        payload = self._request("GET", "/sapi/v1/asset/wallet/balance", signed=True)
        return _rows(payload, "data", "balances")

    def earn_account(self) -> Dict[str, Any]:
        """Simple Earn totals (flexible + locked), valued in BTC and USDT."""

        payload = self._request("GET", "/sapi/v1/simple-earn/account", signed=True)
        return payload if isinstance(payload, dict) else {}

    def earn_flexible_positions(self) -> List[Dict[str, Any]]:
        payload = self._request(
            "GET", "/sapi/v1/simple-earn/flexible/position", params={"size": 100}, signed=True
        )
        return _rows(payload, "rows", "data")

    def earn_locked_positions(self) -> List[Dict[str, Any]]:
        payload = self._request(
            "GET", "/sapi/v1/simple-earn/locked/position", params={"size": 100}, signed=True
        )
        return _rows(payload, "rows", "data")

    def earn_snapshot(self) -> Dict[str, Any]:
        """Savings/Earn holdings, kept separate from tradable stock positions.

        Earn balances are subscribed into products and are not directly
        sellable, so they must never inflate the equity the risk engine sizes
        orders against. They are reported for net-worth display only.
        """

        result: Dict[str, Any] = {
            "total_usdt": 0.0,
            "flexible_usdt": 0.0,
            "locked_usdt": 0.0,
            "flexible": [],
            "locked": [],
            "errors": {},
        }
        try:
            account = self.earn_account()
            result["total_usdt"] = _as_float(account.get("totalAmountInUSDT"))
            result["flexible_usdt"] = _as_float(account.get("totalFlexibleAmountInUSDT"))
            result["locked_usdt"] = _as_float(account.get("totalLockedInUSDT"))
        except (BinanceAPIError, ValueError) as error:
            result["errors"]["account"] = str(error)
        try:
            result["flexible"] = [
                _earn_flexible_row(row) for row in self.earn_flexible_positions()
            ]
        except (BinanceAPIError, ValueError) as error:
            result["errors"]["flexible"] = str(error)
        try:
            result["locked"] = [
                {
                    "asset": str(_first(row, "asset", default="")).upper(),
                    "amount": _as_float(_first(row, "amount")),
                    "duration_days": _as_float(_first(row, "duration")),
                    "accrual_days": _as_float(_first(row, "accrualDays")),
                }
                for row in self.earn_locked_positions()
            ]
        except (BinanceAPIError, ValueError) as error:
            result["errors"]["locked"] = str(error)
        return result

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
        # Authoritative mapping for tokenized holdings (AAPLB -> AAPL).
        resolution = self.asset_resolution_map()

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

                resolved = classify_wallet_asset(asset, resolution, universe, row)
                if resolved is None:
                    unclassified.append({
                        "asset": asset,
                        "wallet": wallet,
                        "total": total,
                        "reason": (
                            "not an equity or tokenized-equity asset" if universe or resolution
                            else "equity universe and tokenized map unavailable"
                        ),
                    })
                    continue

                ticker = resolved["ticker"]
                multiplier = float(resolved["multiplier"])
                entry = positions.setdefault(
                    ticker,
                    {
                        "ticker": ticker,
                        "wallet_assets": [],
                        "quantity": 0.0,
                        "free": 0.0,
                        "locked": 0.0,
                        "wallets": [],
                        "tokenized": False,
                        "multiplier": 1.0,
                        "tradable": ticker in universe if universe else None,
                        "resolved_by": resolved["resolved_by"],
                    },
                )
                # Tokenized balances are share-equivalent only after scaling.
                entry["quantity"] += total * multiplier
                entry["free"] += free * multiplier
                entry["locked"] += locked * multiplier
                if asset not in entry["wallet_assets"]:
                    entry["wallet_assets"].append(asset)
                if wallet not in entry["wallets"]:
                    entry["wallets"].append(wallet)
                if resolved["tokenized"]:
                    entry["tokenized"] = True
                    entry["multiplier"] = multiplier
                    if not resolved.get("multiplier_valid", True):
                        entry["multiplier_stale"] = True

        return {
            "cash_by_asset": cash_by_asset,
            "cash": sum(cash_by_asset.values()),
            "positions": sorted(positions.values(), key=lambda item: item["ticker"]),
            "unclassified_assets": unclassified,
            "equity_universe_size": len(universe),
            "tokenized_map_size": len(resolution),
            "wallet_errors": errors,
            # Savings/Earn is reported for net worth only. It is subscribed into
            # products and not directly sellable, so it must not inflate the
            # equity the risk engine sizes orders against.
            "earn": self.earn_snapshot(),
            "wallet_totals": self._wallet_totals(),
        }

    def _wallet_totals(self) -> List[Dict[str, Any]]:
        try:
            return [
                {
                    "wallet": str(_first(row, "walletName", default="")),
                    "balance_btc": _as_float(_first(row, "balance")),
                    "active": bool(_first(row, "activate", default=True)),
                }
                for row in self.wallet_balances()
            ]
        except (BinanceAPIError, ValueError):
            return []

    # ------------------------------------------------------------------
    # Trading (signed, gated)
    # ------------------------------------------------------------------

    def redeem_flexible(
        self,
        product_id: str,
        *,
        amount: Optional[float] = None,
        redeem_all: bool = False,
        destination: str = "SPOT",
    ) -> Dict[str, Any]:
        """Redeem a Simple Earn flexible position back to a spendable wallet.

        Stock BUY orders draw on ``CARD`` (default) or ``MAIN``; balances still
        subscribed to Earn are not spendable, so funding a purchase from savings
        requires an explicit redemption first. Binance does not auto-redeem.

        ``destination`` accepts ``SPOT`` or ``FUND`` (funding/CARD wallet).
        """

        params: Dict[str, object] = {
            "productId": product_id,
            "destAccount": destination.upper(),
        }
        if redeem_all:
            params["redeemAll"] = "true"
        elif amount is not None and amount > 0.0:
            params["amount"] = self._decimal(amount)
        else:
            raise ValueError("redeem requires either redeem_all=True or a positive amount")
        return self._request(
            "POST", "/sapi/v1/simple-earn/flexible/redeem", params=params, signed=True
        )

    def spendable_balance(self, asset: str, wallet: str = "CARD") -> float:
        """Free balance of ``asset`` in the wallet an order would actually debit."""

        target = asset.upper()
        rows = self.funding_assets() if wallet.upper() == "CARD" else self.spot_assets()
        for row in rows:
            if str(_first(row, "asset", "coin", default="")).upper() == target:
                return _as_float(_first(row, "free", "available"))
        return 0.0

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
        # Sent explicitly rather than relying on the server default, so the
        # settlement currency and funding wallet are always auditable.
        quote_asset = (getattr(order, "quote_asset", "") or "USDC").upper()
        params["quoteAsset"] = quote_asset
        if order.side == "BUY":
            # walletType applies to BUY only; SELL always settles to CARD.
            params["walletType"] = (getattr(order, "wallet_type", "") or "CARD").upper()
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
