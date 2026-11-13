"""Whole-market analysis: trend breadth, BTC lead, volatility regime."""
from __future__ import annotations

from . import indicators as ta


def _btc_regime(candles: list[dict]) -> dict:
    closes = [c["close"] for c in candles]
    e20 = ta.ema(closes, 20)
    e50 = ta.ema(closes, 50)
    r = ta.rsi(closes, 14)
    e20v = next((v for v in reversed(e20) if v is not None), None)
    e50v = next((v for v in reversed(e50) if v is not None), None)
    rv = next((v for v in reversed(r) if v is not None), 50.0)
    price = closes[-1]
    if e20v and e50v:
        if price > e20v > e50v:
            trend = "UP"
        elif price < e20v < e50v:
            trend = "DOWN"
        else:
            trend = "RANGE"
    else:
        trend = "RANGE"
    chg = (price / closes[-25] - 1) * 100 if len(closes) > 25 else 0.0
    return {"trend": trend, "rsi": round(rv, 1),
            "change24h": round(chg, 2), "price": price}


def build_market_regime(tickers: list[dict], btc_candles: list[dict],
                        settings: dict) -> dict:
    """Classify the market so the scanner can throttle in risk-off phases."""
    usdt = [t for t in tickers if t["symbol"].endswith("USDT")]
    min_qv = float(settings.get("min_quote_volume", 5_000_000))
    liquid = [t for t in usdt if t.get("quoteVolume", 0) >= min_qv]
    if not liquid:
        liquid = usdt

    changes = [t["priceChangePercent"] for t in liquid]
    advancers = sum(1 for c in changes if c > 0)
    decliners = len(changes) - advancers
    breadth = advancers / len(changes) * 100 if changes else 50
    avg_chg = sum(changes) / len(changes) if changes else 0.0
    median_chg = sorted(changes)[len(changes) // 2] if changes else 0.0

    # volatility: average |24h change| across majors as a stress proxy
    vol = sum(abs(c) for c in changes) / len(changes) if changes else 0.0

    btc = _btc_regime(btc_candles)

    score = 0
    if btc["trend"] == "UP":
        score += 2
    elif btc["trend"] == "DOWN":
        score -= 2
    score += 1 if breadth >= 60 else (-1 if breadth <= 40 else 0)
    score += 1 if avg_chg > 1 else (-1 if avg_chg < -1 else 0)
    score += 1 if btc["rsi"] >= 55 else (-1 if btc["rsi"] <= 45 else 0)

    if score >= 3:
        regime, advice = "RISK-ON", "Full scan active — take A-grade setups."
    elif score >= 1:
        regime, advice = "CAUTIOUS", "Selective entries — prefer stronger scores."
    elif score >= -1:
        regime, advice = "NEUTRAL", "Reduce position sizes; wait for confirmations."
    else:
        regime, advice = "RISK-OFF", "Capital preservation — mostly cash, no new risk."

    return {
        "regime": regime,
        "advice": advice,
        "score": score,
        "breadth": {"advancers": advancers, "decliners": decliners,
                    "pctUp": round(breadth, 1)},
        "avgChange": round(avg_chg, 2),
        "medianChange": round(median_chg, 2),
        "avgAbsChange": round(vol, 2),
        "btc": btc,
        "tracked": len(liquid),
    }
