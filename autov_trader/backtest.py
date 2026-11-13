"""Simple event-driven backtester for the same analyzer/plan logic.

Conservative assumptions: SL checked before TP inside one candle, taker fee
applied on both sides, no leverage, one position at a time.
"""
from __future__ import annotations

from . import analyzer, binance_client, config


def run_backtest(symbol: str, timeframe: str = "1h", limit: int = 700,
                 settings: dict | None = None) -> dict:
    st = dict(settings or config.load_settings())
    equity0 = float(st.get("account_size", 1000.0))
    fee = float(st.get("fee_pct", 0.1)) / 100.0
    kls = binance_client.client.get_klines(symbol, timeframe, limit)
    if len(kls) < 80:
        return {"error": "not enough history"}

    warmup = 60
    equity = equity0
    peak = equity0
    max_dd = 0.0
    curve = []
    pos = None
    trades = []

    for i in range(warmup, len(kls)):
        window = kls[:i + 1]
        price = kls[i]["close"]
        a = analyzer.analyze_candles(window, st, equity)
        plan = a.get("plan") or {}

        # ---- manage open position with this candle ----
        if pos:
            candle = kls[i]
            exit_px = None
            exit_reason = None
            if candle["low"] <= pos["stop"]:          # conservative: SL first
                exit_px, exit_reason = pos["stop"], "stop-loss"
            else:
                for t in pos["targets"]:
                    if t.get("hit"):
                        continue
                    if candle["high"] >= t["price"]:
                        frac = t.get("fraction", 0.34)
                        qty = pos["qty"] * frac
                        pnl = qty * (t["price"] - pos["entry"])
                        pnl -= (qty * t["price"] + qty * pos["entry"]) * fee
                        equity += pnl
                        pos["qty"] = round(pos["qty"] - qty, 12)
                        pos["pnl_so_far"] = pos.get("pnl_so_far", 0.0) + pnl
                        t["hit"] = True
                        if pos["qty"] <= 1e-9:
                            trades.append({
                                "exit": t["price"], "entry": pos["entry"],
                                "pnl": round(pos["pnl_so_far"], 2),
                                "reason": "TP ladder complete",
                                "openedBar": pos["bar"], "closedBar": i,
                            })
                            pos = None
                        break
            if pos is not None and exit_px:
                qty = pos["qty"]
                pnl = qty * (exit_px - pos["entry"])
                pnl -= (qty * exit_px + qty * pos["entry"]) * fee
                equity += pnl
                trades.append({
                    "exit": exit_px, "entry": pos["entry"],
                    "pnl": round(pnl + pos.get("pnl_so_far", 0.0), 2),
                    "reason": exit_reason,
                    "openedBar": pos["bar"], "closedBar": i,
                })
                pos = None
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

        # ---- look for a fresh entry ----
        if pos is None and plan.get("side") == "LONG" and a["signal"] == "BUY":
            entry = plan["entry"] or price
            stop = plan["stopLoss"]
            qty = plan["position"]["qty"]
            risk_usd = qty * (entry - stop)
            if stop and qty > 0 and risk_usd <= equity * st["risk_per_trade_pct"] / 100 * 1.25:
                # fee-aware entry
                qty = qty * (1 - fee)
                fracs = st.get("tp_fractions", [0.4, 0.3, 0.3])
                pos = {"entry": entry, "stop": stop, "qty": qty,
                       "pnl_so_far": 0.0,
                       "targets": [{"price": float(t["price"]), "hit": False,
                                    "fraction": fracs[j] if j < len(fracs) else 1.0}
                                   for j, t in enumerate(plan["targets"])],
                       "bar": i}
        curve.append(round(equity, 2))

    # force-close at last close
    if pos:
        price = kls[-1]["close"]
        qty = pos["qty"]
        pnl = qty * (price - pos["entry"]) - (qty * price + qty * pos["entry"]) * fee
        equity += pnl
        trades.append({"exit": price, "entry": pos["entry"],
                       "pnl": round(pnl + pos.get("pnl_so_far", 0.0), 2),
                       "reason": "end of data",
                       "openedBar": pos["bar"], "closedBar": len(kls) - 1})
        pos = None
        curve.append(round(equity, 2))

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gw = sum(t["pnl"] for t in wins)
    gl = abs(sum(t["pnl"] for t in losses))
    return {
        "symbol": symbol, "timeframe": timeframe, "candles": len(kls),
        "startEquity": equity0, "endEquity": round(equity, 2),
        "netPnl": round(equity - equity0, 2),
        "returnPct": round((equity / equity0 - 1) * 100, 2),
        "trades": len(trades),
        "winRate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "profitFactor": round(gw / gl, 2) if gl else None,
        "maxDrawdownPct": round(max_dd, 2),
        "avgWin": round(gw / len(wins), 2) if wins else 0,
        "avgLoss": round(-gl / len(losses), 2) if losses else 0,
        "equityCurve": curve[:: max(1, len(curve) // 200)],
        "lastTrades": trades[-15:],
        "note": "Backtest uses the same analyzer + SL/TP rules as live scans. "
                "Past performance ≠ future results.",
    }
