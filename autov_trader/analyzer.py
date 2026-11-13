"""Per-coin chart analysis: score -> signal -> concrete trade plan
(entry / stop-loss / take-profits / position size for the $1000 account)."""
from __future__ import annotations

from . import indicators as ta

VALID_TFS = ("5m", "15m", "30m", "1h", "4h", "1d")


def _last(seq, default=None):
    for v in reversed(seq):
        if v is not None:
            return v
    return default


def analyze_candles(candles: list[dict], settings: dict,
                    equity: float | None = None) -> dict:
    """Return full analysis payload for one symbol."""
    if len(candles) < 60:
        return {"error": "not enough candles", "signal": "NEUTRAL", "score": 0}

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    vols = [c["volume"] for c in candles]
    price = closes[-1]

    e9 = _last(ta.ema(closes, 9))
    e21 = _last(ta.ema(closes, 21))
    e50 = _last(ta.ema(closes, 50))
    e200 = _last(ta.ema(closes, 200)) if len(closes) >= 200 else None
    rsi_v = _last(ta.rsi(closes, 14), 50.0)
    macd_l, macd_s, macd_h = ta.macd(closes)
    macd_hist = _last(macd_h, 0.0) or 0.0
    macd_hist_prev = next((v for v in reversed(macd_h[:-1]) if v is not None), 0.0) or 0.0
    _bb_lo, _bb_mid, _bb_hi = ta.bollinger(closes, 20, 2.0)
    bb_l, bb_m, bb_u = _last(_bb_lo), _last(_bb_mid), _last(_bb_hi)
    atr_v = _last(ta.atr(highs, lows, closes, 14), price * 0.01) or price * 0.01
    adx_v = _last(ta.adx(highs, lows, closes, 14), 20.0) or 20.0
    stoch_k, stoch_d = ta.stochastic(highs, lows, closes)
    k_v = _last(stoch_k, 50.0) or 50.0
    levels = ta.swing_levels(highs, lows)
    patterns = ta.detect_patterns(candles)

    atr_pct = atr_v / price * 100.0
    vol_recent = sum(vols[-5:]) / 5
    vol_base = sum(vols[-30:]) / 30 or 1.0
    vol_ratio = vol_recent / vol_base

    # ---------------- scoring ----------------
    checks = []  # (name, points, note)  positive = bullish

    # trend structure
    trend_pts = 0
    if e9 and e21 and e50:
        if e9 > e21 > e50:
            trend_pts += 30
        elif e9 < e21 < e50:
            trend_pts -= 30
        else:
            trend_pts += 5 if e9 > e21 else -5
    if price > (e50 or price):
        trend_pts += 10
    else:
        trend_pts -= 10
    if e200:
        trend_pts += 10 if price > e200 else -10
    checks.append(("Trend (EMA 9/21/50/200)", trend_pts,
                   f"EMA9={_fmt(e9)} EMA21={_fmt(e21)} EMA50={_fmt(e50)}"))

    # momentum: RSI
    if rsi_v < 30:
        rsi_pts = 25
        note = f"RSI {rsi_v:.1f} oversold"
    elif rsi_v < 45:
        rsi_pts = 12
        note = f"RSI {rsi_v:.1f} rising zone"
    elif rsi_v > 75:
        rsi_pts = -25
        note = f"RSI {rsi_v:.1f} overbought"
    elif rsi_v > 65:
        rsi_pts = 5
        note = f"RSI {rsi_v:.1f} strong but hot"
    else:
        rsi_pts = 0
        note = f"RSI {rsi_v:.1f} neutral"
    checks.append(("RSI(14)", rsi_pts, note))

    # MACD histogram direction
    if macd_hist > 0 and macd_hist > macd_hist_prev:
        macd_pts = 20
    elif macd_hist > 0:
        macd_pts = 10
    elif macd_hist < 0 and macd_hist < macd_hist_prev:
        macd_pts = -20
    elif macd_hist < 0:
        macd_pts = -10
    else:
        macd_pts = 0
    checks.append(("MACD histogram", macd_pts,
                   f"hist={macd_hist:.6g}, prev={macd_hist_prev:.6g}"))

    # Bollinger position
    if bb_u and bb_l:
        width = (bb_u - bb_l) / price * 100
        pos = (price - bb_l) / max(bb_u - bb_l, 1e-12)
        if pos < 0.15:
            bb_pts, bnote = 15, f"at lower band (squeeze pos {pos:.2f}, width {width:.2f}%)"
        elif pos > 0.9:
            bb_pts, bnote = -10, f"at upper band (pos {pos:.2f})"
        else:
            bb_pts, bnote = 0, f"mid band (pos {pos:.2f})"
        checks.append(("Bollinger(20,2)", bb_pts, bnote))

    # ADX trend strength (amplifies trend direction)
    adx_pts = 0
    if adx_v >= 25:
        adx_pts = 10 if trend_pts > 0 else -10
    checks.append(("ADX trend strength", adx_pts, f"ADX {adx_v:.1f}"))

    # stochastic
    if k_v < 25 and _last(stoch_d, 50) is not None:
        st_pts = 8 if k_v >= (_last(stoch_d, 50) or 0) else 5
        st_note = f"%K {k_v:.1f} (oversold zone)"
    elif k_v > 85:
        st_pts, st_note = -8, f"%K {k_v:.1f} (overbought zone)"
    else:
        st_pts, st_note = 0, f"%K {k_v:.1f}"
    checks.append(("Stochastic", st_pts, st_note))

    # volume confirmation
    if vol_ratio > 1.4:
        vol_pts = 12 if trend_pts >= 0 else -6
        vnote = f"volume {vol_ratio:.2f}x baseline (confirmed move)"
    elif vol_ratio < 0.7:
        vol_pts = -6
        vnote = f"volume {vol_ratio:.2f}x baseline (weak)"
    else:
        vol_pts, vnote = 0, f"volume {vol_ratio:.2f}x baseline"
    checks.append(("Volume", vol_pts, vnote))

    # candlestick patterns
    pat_pts = 0
    for p in patterns:
        if p in ("Bullish Engulfing", "Hammer", "Resistance Breakout"):
            pat_pts += 8
        elif p in ("Bearish Engulfing", "Shooting Star", "Support Breakdown"):
            pat_pts -= 8
    checks.append(("Candle patterns", pat_pts, ", ".join(patterns) or "none"))

    score = sum(p for _, p, _ in checks)
    score = max(-100, min(100, score))

    if score >= 35:
        signal = "BUY"
        confidence = min(95, 50 + int(score * 0.45))
    elif score >= 18:
        signal = "WEAK_BUY"
        confidence = 40 + int(score * 0.5)
    elif score <= -35:
        signal = "SELL"
        confidence = min(95, 50 + int(abs(score) * 0.45))
    elif score <= -18:
        signal = "WEAK_SELL"
        confidence = 40 + int(abs(score) * 0.5)
    else:
        signal, confidence = "NEUTRAL", max(20, 50 - abs(score))

    plan = _build_plan(signal, score, price, atr_v, levels, highs, lows,
                       settings, equity or settings.get("account_size", 1000.0))

    return {
        "price": price,
        "score": score,
        "signal": signal,
        "confidence": confidence,
        "checks": [{"name": n, "points": p, "note": note} for n, p, note in checks],
        "indicators": {
            "ema9": _round(e9), "ema21": _round(e21),
            "ema50": _round(e50), "ema200": _round(e200),
            "rsi": round(rsi_v, 2),
            "macd": _round(_last(macd_l)), "macdSignal": _round(_last(macd_s)),
            "macdHist": round(macd_hist, 8),
            "bbLower": _round(bb_l), "bbMid": _round(bb_m),
            "bbUpper": _round(bb_u),
            "atr": _round(atr_v), "atrPct": round(atr_pct, 3),
            "adx": round(adx_v, 1),
            "stochK": round(k_v, 1),
            "volRatio": round(vol_ratio, 2),
        },
        "levels": levels,
        "patterns": patterns,
        "plan": plan,
    }


def _build_plan(signal: str, score: int, price: float, atr: float,
                levels: dict, highs, lows, settings: dict,
                equity: float) -> dict:
    """Concrete entry / SL / TP ladder + position sizing."""
    if signal not in ("BUY", "WEAK_BUY"):
        # For shorts (spot): show "exit / avoid" guidance only.
        if signal in ("SELL", "WEAK_SELL"):
            return {
                "side": "SHORT_WATCH",
                "reason": "Bearish setup — avoid new buys; consider trimming "
                          "existing holdings. Spot shorts are not executed.",
                "entry": None, "stopLoss": None, "targets": [],
            }
        return {"side": "NONE", "reason": "No edge — wait.", "entry": None,
                "stopLoss": None, "targets": []}

    atr_mult = float(settings.get("atr_sl_mult", 1.8))
    sl_by_atr = price - atr * atr_mult
    sl_by_swing = levels["support"] - atr * 0.35
    stop = max(sl_by_atr, min(sl_by_swing, price * 0.985))  # never risk > ~2.5%
    risk_per_unit = price - stop
    if risk_per_unit <= 0:
        stop = price * 0.98
        risk_per_unit = price - stop

    risk_pct = float(settings.get("risk_per_trade_pct", 0.5))
    risk_usd = equity * risk_pct / 100.0
    qty = risk_usd / risk_per_unit
    notional = qty * price
    max_notional = equity * float(settings.get("max_per_symbol_pct", 25.0)) / 100.0
    if notional > max_notional:
        notional = max_notional
        qty = notional / price
        risk_usd = qty * risk_per_unit

    rr_targets = settings.get("rr_targets", [1.5, 3.0, 5.0])
    resist = levels["resistance"]
    targets = []
    for i, rr in enumerate(rr_targets, start=1):
        tp_price = price + risk_per_unit * rr
        capped = tp_price > resist and i == 1 and resist > price
        if capped:
            tp_price = resist * 0.999  # take profit before known resistance
        targets.append({
            "n": i,
            "price": _round(tp_price),
            "rr": round((tp_price - price) / risk_per_unit, 2),
            "pct": round((tp_price / price - 1) * 100, 3),
            "usd": round(qty * (tp_price - price), 2),
            "note": "capped at resistance" if capped else "",
        })

    return {
        "side": "LONG",
        "reason": f"Bullish composite score {score:+d} — ATR-based protection "
                  f"with R-multiple targets.",
        "entry": _round(price),
        "entryType": "market (or limit on pullback to EMA9)",
        "stopLoss": _round(stop),
        "stopPct": round((1 - stop / price) * 100, 3),
        "riskUsd": round(risk_usd, 2),
        "targets": targets,
        "position": {
            "qty": round(qty, 6),
            "notionalUsd": round(notional, 2),
            "riskUsd": round(risk_usd, 2),
            "riskPct": round(risk_usd / equity * 100, 3) if equity else 0,
            "equity": round(equity, 2),
        },
        "rr": round((targets[0]["price"] - price) / risk_per_unit, 2) if targets else 0,
    }


def _fmt(v):
    return None if v is None else _round(v)


def _round(v, nd=8):
    if v is None:
        return None
    if v >= 1000:
        return round(v, 2)
    if v >= 1:
        return round(v, 4)
    return round(v, nd)
