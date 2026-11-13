"""Binance REST client with signed-order support and graceful demo fallback.

Live endpoints tried in order: api.binance.com -> data-api.binance.vision
(public data only). If neither is reachable (e.g. inside a sandbox) the client
switches to deterministic demo data and reports `live_data=False`.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from urllib.parse import urlencode

import requests

from . import config, demo_data

log = logging.getLogger("autov.binance")

BASES = ["https://api.binance.com", "https://data-api.binance.vision"]
TIMEOUT = 8

# block stablecoins / fiat / leveraged tokens from the scanner
_EXCLUDE_SUFFIX = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")
_EXCLUDE_BASE = {
    "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "EUR", "TRY", "BRL",
    "ARS", "GBP", "JPY", "AUD", "C2USD", "AEUR", "EURI", "USDD", "USD1",
    "XUSD", "USDE",
}


class BinanceClient:
    def __init__(self) -> None:
        self._live: bool | None = None       # None = unknown, False = demo
        self._base: str | None = None
        self._lock = threading.Lock()
        self._session = requests.Session()

    # ---------- connectivity / data mode ----------
    @property
    def live_data(self) -> bool:
        if self._live is None:
            self._probe()
        return bool(self._live)

    @property
    def data_source(self) -> str:
        if config.env("DATA_MODE", "auto") == "demo":
            self._live = False
            return "demo (forced)"
        if self.live_data and self._base:
            return self._base.replace("https://", "")
        return "demo (offline fallback)"

    def _probe(self) -> None:
        mode = config.env("DATA_MODE", "auto").lower()
        if mode == "demo":
            self._live = False
            return
        with self._lock:
            if self._live is not None:
                return
            for base in BASES:
                try:
                    self._session.get(f"{base}/api/v3/ping", timeout=TIMEOUT)
                    self._base, self._live = base, True
                    log.info("live data via %s", base)
                    return
                except requests.RequestException:
                    continue
            self._live = False
            self._base = None
            log.warning("Binance unreachable -> demo data fallback")

    def _public(self, path: str, params: dict | None = None) -> object:
        if not self.live_data:
            raise ConnectionError("demo mode")
        assert self._base
        url = f"{self._base}{path}"
        for attempt in range(2):
            try:
                r = self._session.get(url, params=params, timeout=TIMEOUT)
                if r.status_code == 429 or r.status_code == 418:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json()
            except requests.RequestException:
                if attempt:
                    self._live = False
                    raise
                time.sleep(0.4)
        raise ConnectionError("binance public endpoint failed")

    # ---------- market data ----------
    def get_klines(self, symbol: str, interval: str = "1h",
                   limit: int = 300) -> list[dict]:
        limit = min(limit, 1000)
        if self.live_data:
            try:
                raw = self._public("/api/v3/klines", {
                    "symbol": symbol, "interval": interval, "limit": limit})
                return [{
                    "openTime": int(k[0]),
                    "open": float(k[1]), "high": float(k[2]),
                    "low": float(k[3]), "close": float(k[4]),
                    "volume": float(k[5]),
                    "quoteVolume": float(k[7]), "trades": int(k[8]),
                } for k in raw]
            except (ConnectionError, OSError):
                self._live = False
        return demo_data.make_klines(symbol, interval, limit)

    def get_tickers(self) -> list[dict]:
        if self.live_data:
            try:
                raw = self._public("/api/v3/ticker/24hr")
                return [{
                    "symbol": t["symbol"],
                    "lastPrice": float(t["lastPrice"]),
                    "priceChangePercent": float(t["priceChangePercent"]),
                    "quoteVolume": float(t["quoteVolume"]),
                    "highPrice": float(t["highPrice"]),
                    "lowPrice": float(t["lowPrice"]),
                    "count": int(t["count"]),
                } for t in raw]
            except (ConnectionError, OSError):
                self._live = False
        return demo_data.demo_universe()

    def get_exchange_info(self) -> dict:
        """Filters (tick size / step size / min qty) per symbol."""
        if self.live_data:
            try:
                raw = self._public("/api/v3/exchangeInfo")
                out = {}
                for s in raw.get("symbols", []):
                    f = {x["filterType"]: x for x in s.get("filters", [])}
                    price_tick = float(f.get("PRICE_FILTER", {}).get("tickSize", "0.01"))
                    lot_step = float(f.get("LOT_SIZE", {}).get("stepSize", "0.000001"))
                    min_qty = float(f.get("LOT_SIZE", {}).get("minQty", lot_step))
                    out[s["symbol"]] = {
                        "tickSize": price_tick, "stepSize": lot_step,
                        "minQty": min_qty, "status": s.get("status", "TRADING"),
                    }
                return out
            except (ConnectionError, OSError):
                self._live = False
        return {}

    # ---------- signed (account / orders) ----------
    def _signed(self, path: str, method: str = "GET", params: dict | None = None) -> object:
        if not config.API_KEY or not config.API_SECRET:
            raise PermissionError("API keys not configured")
        if not self.live_data:
            raise ConnectionError("demo mode: signed calls need live data")
        assert self._base and self._base.startswith("https://api.binance.com")
        params = dict(params or {})
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        query = urlencode(params)
        sig = hmac.new(config.API_SECRET.encode(), query.encode(),
                       hashlib.sha256).hexdigest()
        url = f"{self._base}{path}?{query}&signature={sig}"
        headers = {"X-MBX-APIKEY": config.API_KEY}
        r = self._session.request(method, url, headers=headers, timeout=TIMEOUT)
        if r.status_code >= 400:
            raise RuntimeError(f"Binance {r.status_code}: {r.text[:300]}")
        return r.json()

    def account_balance_usdt(self) -> float | None:
        """Free USDT balance. None when unavailable (demo / no keys)."""
        try:
            acct = self._signed("/api/v3/account")
            for b in acct.get("balances", []):
                if b["asset"] == "USDT":
                    return float(b["free"]) + float(b["locked"])
        except Exception as e:  # noqa: BLE001 - report via status, never crash UI
            log.info("balance unavailable: %s", e)
        return None

    def market_buy(self, symbol: str, quote_amount: float) -> dict:
        """Live spot market buy for `quote_amount` USDT (notional)."""
        info = self.get_exchange_info().get(symbol, {})
        price = float(self._public("/api/v3/ticker/price", {"symbol": symbol})["price"])
        step = info.get("stepSize", 0.000001)
        min_qty = info.get("minQty", step)
        qty = quote_amount / price
        qty = _round_to(qty, step)
        if qty < min_qty:
            raise ValueError(f"qty {qty} below min {min_qty}")
        return self._signed("/api/v3/order", "POST", {
            "symbol": symbol, "side": "BUY", "type": "MARKET",
            "quantity": _fmt(qty),
        })

    def place_exit_orders(self, symbol: str, quantity: float,
                          take_profit: float, stop_loss: float) -> dict:
        """TP limit + SL stop-market as separate orders (spot, one-way)."""
        info = self.get_exchange_info().get(symbol, {})
        qty = _round_to(quantity, info.get("stepSize", 0.000001))
        results = {}
        results["tp"] = self._signed("/api/v3/order", "POST", {
            "symbol": symbol, "side": "SELL", "type": "LIMIT",
            "timeInForce": "GTC", "quantity": _fmt(qty),
            "price": _fmt(_round_to(take_profit, info.get("tickSize", 0.01))),
        })
        results["sl"] = self._signed("/api/v3/order", "POST", {
            "symbol": symbol, "side": "SELL", "type": "STOP_MARKET",
            "quantity": _fmt(qty),
            "stopPrice": _fmt(_round_to(stop_loss, info.get("tickSize", 0.01))),
        })
        return results

    def cancel_open_orders(self, symbol: str) -> None:
        try:
            self._signed("/api/v3/openOrders", "DELETE", {"symbol": symbol})
        except Exception as e:  # noqa: BLE001
            log.info("cancel open orders: %s", e)


def _round_to(value: float, step: float) -> float:
    if step <= 0:
        return value
    precision = max(0, int(round(-__import__("math").log10(step))))
    return round(round(value / step) * step, precision)


def _fmt(value: float) -> str:
    s = f"{value:.10f}".rstrip("0").rstrip(".")
    return s or "0"


client = BinanceClient()
