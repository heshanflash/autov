"""Pure-python technical indicators (no numpy/pandas needed)."""
from __future__ import annotations

import math


def ema(values: list[float], period: int) -> list[float | None]:
    if not values:
        return []
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    run = sum(values[:period])
    out[period - 1] = run / period
    for i in range(period, len(values)):
        run += values[i] - values[i - period]
        out[i] = run / period
    return out


def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_g, avg_l = gains / period, losses / period
    out[period] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1 + avg_g / avg_l)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
        out[i] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1 + avg_g / avg_l)
    return out


def macd(closes: list[float], fast: int = 12, slow: int = 26,
         signal: int = 9) -> tuple[list, list, list]:
    ef, es = ema(closes, fast), ema(closes, slow)
    line = [None if (a is None or b is None) else a - b for a, b in zip(ef, es)]
    # signal EMA over the defined part of macd line
    defined = [v for v in line if v is not None]
    sig_defined = ema(defined, signal) if defined else []
    sig: list = [None] * len(line)
    j = 0
    for i, v in enumerate(line):
        if v is not None:
            sig[i] = sig_defined[j] if j < len(sig_defined) else None
            j += 1
    hist = [None if (a is None or b is None) else a - b for a, b in zip(line, sig)]
    return line, sig, hist


def bollinger(closes: list[float], period: int = 20,
              mult: float = 2.0) -> tuple[list, list, list]:
    mid = sma(closes, period)
    upper: list = [None] * len(closes)
    lower: list = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        m = mid[i]
        var = sum((x - m) ** 2 for x in window) / period
        sd = math.sqrt(var)
        upper[i] = m + mult * sd
        lower[i] = m - mult * sd
    return lower, mid, upper


def atr(highs: list[float], lows: list[float], closes: list[float],
        period: int = 14) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < 2:
        return out
    trs = [highs[0] - lows[0]]
    for i in range(1, n):
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    if n <= period:
        return out
    prev = sum(trs[1:period + 1]) / period
    out[period] = prev
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


def adx(highs: list[float], lows: list[float], closes: list[float],
        period: int = 14) -> list[float | None]:
    """Wilder-style ADX (simplified single-pass)."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < period * 2 + 2:
        return out
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    m = len(trs)
    atr_v = sum(trs[:period])
    pdm, mdm = sum(plus_dm[:period]), sum(minus_dm[:period])
    dxs = []
    for i in range(period, m):
        if i > period:
            atr_v = atr_v - atr_v / period + trs[i]
            pdm = pdm - pdm / period + plus_dm[i]
            mdm = mdm - mdm / period + minus_dm[i]
        pdi = 100 * pdm / atr_v if atr_v else 0.0
        mdi = 100 * mdm / atr_v if atr_v else 0.0
        dx = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0
        dxs.append(dx)
    if len(dxs) < period:
        return out
    adx_v = sum(dxs[:period]) / period
    out_idx = period + period  # aligns approximately with candle index
    if out_idx < n:
        out[out_idx] = adx_v
    for i in range(period, len(dxs)):
        adx_v = (adx_v * (period - 1) + dxs[i]) / period
        oi = period + i + 1
        if oi < n:
            out[oi] = adx_v
    return out


def stochastic(highs, lows, closes, k_period=14, d_period=3):
    n = len(closes)
    k: list[float | None] = [None] * n
    for i in range(k_period - 1, n):
        hh = max(highs[i - k_period + 1:i + 1])
        ll = min(lows[i - k_period + 1:i + 1])
        k[i] = 50.0 if hh == ll else 100.0 * (closes[i] - ll) / (hh - ll)
    d = sma([x if x is not None else 50.0 for x in k], d_period)
    d = [None if i < k_period - 1 + d_period - 1 else d[i] for i in range(n)]
    return k, d


def swing_levels(highs, lows, lookback: int = 60, wing: int = 3) -> dict:
    """Recent swing highs/lows used as support/resistance."""
    h = highs[-lookback:]
    l = lows[-lookback:]
    hi, lo = max(h), min(l)
    res, sup = [], []
    for i in range(wing, len(h) - wing):
        if h[i] == max(h[i - wing:i + wing + 1]):
            res.append(h[i])
        if l[i] == min(l[i - wing:i + wing + 1]):
            sup.append(l[i])
    return {
        "resistance": round(max(res), 8) if res else round(hi, 8),
        "support": round(min(sup), 8) if sup else round(lo, 8),
        "range_high": round(hi, 8),
        "range_low": round(lo, 8),
    }


def detect_patterns(candles: list[dict]) -> list[str]:
    """A few reliable single/double candlestick patterns."""
    out = []
    if len(candles) < 3:
        return out
    c1, c2 = candles[-2], candles[-1]
    o1, h1, l1, cl1 = c1["open"], c1["high"], c1["low"], c1["close"]
    o2, h2, l2, cl2 = c2["open"], c2["high"], c2["low"], c2["close"]
    body1, body2 = abs(cl1 - o1), abs(cl2 - o2)
    rng = h2 - l2 or 1e-12
    upper = h2 - max(o2, cl2)
    lower = min(o2, cl2) - l2

    if cl2 > o2 and cl1 < o1 and cl2 >= o1 and o2 <= cl1 and body2 > body1:
        out.append("Bullish Engulfing")
    if cl2 < o2 and cl1 > o1 and cl2 <= o1 and o2 >= cl1 and body2 > body1:
        out.append("Bearish Engulfing")
    if lower > 2 * body2 and upper < body2 and cl2 > o2:
        out.append("Hammer")
    if upper > 2 * body2 and lower < body2 and cl2 < o2:
        out.append("Shooting Star")
    if body1 < rng * 0.1 and body2 < rng * 0.1:
        out.append("Indecision (Doji)")
    # higher-high continuation
    if cl2 > h1 and cl2 > o2:
        out.append("Resistance Breakout")
    if cl2 < l1 and cl2 < o2:
        out.append("Support Breakdown")
    return out
