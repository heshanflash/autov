"""Scanner: analyze the whole USDT universe in parallel and cache results."""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import analyzer, binance_client, config, market, portfolio, risk

log = logging.getLogger("autov.scanner")

_cache: dict = {"data": None, "at": 0.0, "lock": threading.Lock()}
CACHE_TTL = 60  # seconds

_STABLE = ("USDT", "USDC", "FDUSD", "TUSD", "BUSD", "DAI")


def _tradable_universe(tickers: list[dict], limit: int) -> list[dict]:
    from .binance_client import _EXCLUDE_BASE, _EXCLUDE_SUFFIX
    out = []
    for t in tickers:
        sym = t["symbol"]
        if not sym.endswith("USDT"):
            continue
        base = sym[:-4]
        if base in _EXCLUDE_BASE or sym.endswith(_EXCLUDE_SUFFIX):
            continue
        if t.get("quoteVolume", 0) < config.load_settings()["min_quote_volume"]:
            continue
        out.append(t)
    return out[:limit]


def run_scan(force: bool = False, timeframe: str | None = None) -> dict:
    """Full market pass -> regime + per-coin analysis + trade plans."""
    st = config.load_settings()
    tf = timeframe or st["timeframe"]
    if tf not in analyzer.VALID_TFS:
        tf = "1h"

    with _cache["lock"]:
        if (not force and _cache["data"] and _cache["data"].get("tf") == tf
                and time.time() - _cache["at"] < CACHE_TTL):
            cached = dict(_cache["data"])
            cached["cached"] = True
            return cached

    tickers = binance_client.client.get_tickers()
    universe = _tradable_universe(tickers, st["scan_limit"])
    btc_candles = binance_client.client.get_klines("BTCUSDT", "4h", 120)
    regime = market.build_market_regime(tickers, btc_candles, st)

    # sizes & risk checks use the risk manager's view of equity
    equity_now = st["account_size"] + risk.snapshot()["monthPnl"]

    results: list[dict] = []

    def work(tk: dict) -> dict | None:
        try:
            kls = binance_client.client.get_klines(tk["symbol"], tf, 300)
            a = analyzer.analyze_candles(kls, st, equity_now)
            if "error" in a:
                return None
            a.update({
                "symbol": tk["symbol"],
                "lastPrice": tk["lastPrice"],
                "change24h": tk["priceChangePercent"],
                "quoteVolume": tk["quoteVolume"],
                "tf": tf,
            })
            return a
        except Exception as e:  # noqa: BLE001
            log.debug("scan %s failed: %s", tk["symbol"], e)
            return None

    max_workers = 16 if binance_client.client.live_data else 8
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(work, t) for t in universe]
        for f in as_completed(futs):
            r = f.result()
            if r:
                results.append(r)

    results.sort(key=lambda x: -abs(x["score"]))

    # auto-manage paper positions with fresh prices/candles
    prices = {r["symbol"]: r["price"] for r in results}
    events = []
    if st["trading_mode"] == "paper" and prices:
        open_syms = {p["symbol"] for p in portfolio.status()["openPositions"]}
        candles_by_sym = {
            sym: binance_client.client.get_klines(sym, tf, 10)
            for sym in open_syms & prices.keys()
        }
        events = portfolio.mark_and_manage(prices, candles_by_sym)

    snap = risk.snapshot()
    payload = {
        "tf": tf,
        "generatedAt": int(time.time() * 1000),
        "dataSource": binance_client.client.data_source,
        "liveData": binance_client.client.live_data,
        "regime": regime,
        "risk": snap,
        "coins": results,
        "manageEvents": events,
        "equity": equity_now,
        "cached": False,
    }
    with _cache["lock"]:
        _cache["data"] = payload
        _cache["at"] = time.time()
    return payload


def scan_stats(scan: dict) -> dict:
    coins = scan["coins"]
    buy = sum(1 for c in coins if c["signal"] == "BUY")
    weak_buy = sum(1 for c in coins if c["signal"] == "WEAK_BUY")
    sell = sum(1 for c in coins if c["signal"] in ("SELL", "WEAK_SELL"))
    return {"scanned": len(coins), "buy": buy, "weakBuy": weak_buy,
            "sell": sell, "neutral": len(coins) - buy - weak_buy - sell}
