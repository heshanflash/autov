"""Deterministic synthetic market data used when Binance is unreachable.

Generates realistic OHLCV candles (trend + seasonality + noise + volatility
clusters) so the app is fully explorable without network access. Every symbol
gets a stable seed, so charts stay consistent between requests.
"""
from __future__ import annotations

import hashlib
import math
import random
import time

# Rough anchor prices (USDT) for well-known coins; everything else is derived.
_ANCHORS = {
    "BTC": 96000.0, "ETH": 3300.0, "SOL": 190.0, "BNB": 690.0, "XRP": 2.3,
    "DOGE": 0.34, "ADA": 0.95, "AVAX": 38.0, "LINK": 22.0, "DOT": 7.0,
    "TRX": 0.25, "MATIC": 0.45, "NEAR": 5.5, "APT": 9.0, "ARB": 0.85,
    "OP": 1.8, "LTC": 105.0, "ATOM": 6.5, "UNI": 13.0, "INJ": 24.0,
    "SUI": 4.2, "TIA": 5.5, "SEI": 0.45, "RUNE": 5.0, "FIL": 5.5,
    "AAVE": 320.0, "MKR": 1600.0, "PEPE": 0.0000185, "SHIB": 0.000023,
    "BONK": 0.000034, "WIF": 2.6, "ORDI": 40.0, "STX": 1.9, "ICP": 10.5,
    "HBAR": 0.28, "VET": 0.045, "ALGO": 0.35, "SAND": 0.5, "MANA": 0.45,
    "GALA": 0.035, "AXS": 6.5, "ENJ": 0.25, "CHZ": 0.09, "FTM": 1.1,
    "ONE": 0.02, "IOTA": 0.28, "XLM": 0.4, "ETC": 30.0, "BCH": 480.0,
    "EOS": 0.8, "THETA": 2.0, "FLOW": 0.7, "EGLD": 35.0, "ROSE": 0.08,
    "CELO": 0.75, "KAVA": 0.5, "ZIL": 0.02, "WAVES": 1.5, "ONT": 0.85,
    "QTUM": 3.5, "LSK": 1.2, "DASH": 30.0, "ZEC": 55.0, "XMR": 180.0,
}

_INTERVAL_S = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600,
               "4h": 14400, "1d": 86400}


def _seed(symbol: str) -> int:
    return int(hashlib.sha256(symbol.encode()).hexdigest()[:12], 16)


def anchor_price(symbol: str) -> float:
    base = symbol.replace("USDT", "")
    if base in _ANCHORS:
        return _ANCHORS[base]
    h = _seed(symbol) % 10_000
    # Spread generated prices across sub-cent .. few hundred dollars
    if h % 5 == 0:
        return round(50 + (h % 300) * 0.4, 2)
    if h % 3 == 0:
        return round(0.5 + (h % 400) / 100.0, 3)
    return round(0.002 + (h % 900) / 5000.0, 6)


def make_klines(symbol: str, interval: str, limit: int = 300,
                end_time_ms: int | None = None) -> list[dict]:
    """Return candle dicts matching Binance kline fields (open time first)."""
    step_ms = _INTERVAL_S.get(interval, 3600) * 1000
    end = end_time_ms or (int(time.time() // (_INTERVAL_S.get(interval, 3600))) * _INTERVAL_S.get(interval, 3600)) * 1000
    start_open = end - step_ms * limit

    rnd = random.Random(_seed(symbol) ^ (step_ms // 1000))
    price = anchor_price(symbol)
    # regime: each symbol leans trend-following in one direction for a while
    drift = rnd.uniform(-0.0006, 0.0009)          # per-candle drift
    vol = rnd.uniform(0.004, 0.016)               # per-candle sigma
    seasonality = rnd.uniform(0.0, math.tau)
    vol_cluster = vol

    candles = []
    t = start_open
    for i in range(limit):
        # volatility clustering (GARCH-ish) + slow sine regime
        vol_cluster = max(0.0015, 0.9 * vol_cluster + 0.1 * vol * rnd.uniform(0.5, 1.6))
        wave = math.sin(seasonality + i / max(8.0, limit / 18.0)) * 0.0009
        ret = rnd.gauss(drift + wave, vol_cluster)
        o = price
        c = price * (1.0 + ret)
        wick = abs(rnd.gauss(0, vol_cluster * 0.7))
        h = max(o, c) * (1.0 + wick)
        l = min(o, c) * (1.0 - wick)
        base_vol = 1_000_000 + (_seed(symbol) % 5_000_000)
        v = base_vol * (0.6 + abs(ret) / max(vol_cluster, 1e-9) * 0.35 + rnd.random() * 0.5)
        q = v * (o + c) / 2
        candles.append({
            "openTime": int(t),
            "open": o, "high": h, "low": l, "close": c,
            "volume": v, "quoteVolume": q,
            "trades": int(500 + rnd.random() * 4000),
        })
        price = max(c, 1e-12)
        t += step_ms
    # make last close land near the current "price" of the anchor
    return candles


def demo_universe(limit: int = 40) -> list[dict]:
    """Fake 24h tickers for the scanner in demo mode."""
    out = []
    symbols = list(_ANCHORS.keys())[:limit]
    extra = 0
    while len(symbols) < limit:
        symbols.append(f"ALT{extra}USDT")
        extra += 1
    rnd = random.Random(1337)
    for b in symbols:
        sym = f"{b}USDT"
        price = anchor_price(sym)
        chg = rnd.uniform(-6.5, 7.5)
        qv = rnd.uniform(6e6, 9e8)
        out.append({
            "symbol": sym,
            "lastPrice": price,
            "priceChangePercent": chg,
            "quoteVolume": qv,
            "highPrice": price * (1 + abs(chg) / 200 + 0.01),
            "lowPrice": price * (1 - abs(chg) / 200 - 0.01),
            "count": int(rnd.uniform(5000, 200000)),
        })
    out.sort(key=lambda x: -x["quoteVolume"])
    return out
