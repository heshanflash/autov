"""Paper-trading portfolio: ledger, open positions, SL/TP management,
equity curve and the day-by-day plan your $1000 account follows."""
from __future__ import annotations

import json
import threading
import time
import uuid

from . import config, risk

LEDGER = config.STATE_DIR / "portfolio.json"
_lock = threading.RLock()


def _blank() -> dict:
    st = config.load_settings()
    return {
        "cash": st["account_size"],
        "startEquity": st["account_size"],
        "positions": [],
        "trades": [],
        "equityCurve": [{"t": int(time.time() * 1000),
                         "equity": st["account_size"]}],
        "snapshots": {},   # date_iso -> {pnl, trades}
    }


def _load() -> dict:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return _blank()


def _save(s: dict) -> None:
    config.STATE_DIR.mkdir(exist_ok=True)
    LEDGER.write_text(json.dumps(s, indent=2), encoding="utf-8")


def equity(s: dict | None = None) -> float:
    s = s or _load()
    return s["cash"] + sum(p["qty"] * p["mark"] for p in s["positions"])


def reset(account_size: float | None = None) -> dict:
    with _lock:
        st = config.load_settings()
        size = float(account_size or st["account_size"])
        _save(_blank_reset(size))
        risk.reset_all(size)
    return {**status(), "risk": risk.snapshot()}


def _blank_reset(size: float) -> dict:
    b = _blank()
    b["cash"] = size
    b["startEquity"] = size
    b["equityCurve"] = [{"t": int(time.time() * 1000), "equity": size}]
    return b


def open_position(symbol: str, plan: dict, price: float,
                  analysis_meta: dict | None = None) -> dict:
    """Try to open a paper position respecting every risk gate."""
    if plan.get("side") != "LONG":
        return {"ok": False, "error": f"plan side {plan.get('side')} not executable"}
    entry = float(plan.get("entry") or price)
    stop = float(plan["stopLoss"])
    targets = plan.get("targets", [])
    if not targets:
        return {"ok": False, "error": "plan has no take-profit targets"}
    pos_info = plan.get("position", {})
    qty = float(pos_info.get("qty") or 0)
    if qty <= 0:
        return {"ok": False, "error": "invalid position qty"}

    with _lock:
        s = _load()
        eq = s["cash"] + sum(p["qty"] * p["mark"] for p in s["positions"])
        notional = qty * entry
        if notional > s["cash"]:
            qty = s["cash"] / entry
            notional = qty * entry
            if notional < 10:
                return {"ok": False, "error": "insufficient paper cash"}
        exposure_pct = sum(p["qty"] * p["mark"] for p in s["positions"]
                           if p["symbol"] == symbol) / eq * 100 if eq else 0
        risk_usd = qty * (entry - stop)
        allowed, reason = risk.can_open(risk_usd, len(s["positions"]),
                                        exposure_pct)
        if not allowed:
            return {"ok": False, "error": reason}

        st = config.load_settings()
        # fraction ladder TP1..TP3 with remainder after TP3
        fr = list(st.get("tp_fractions", [0.4, 0.3, 0.3]))
        pos = {
            "id": uuid.uuid4().hex[:12],
            "symbol": symbol,
            "qty": round(qty, 8),
            "entry": entry,
            "mark": price,
            "stop": stop,
            "targets": [{"price": float(t["price"]),
                         "fraction": fr[i] if i < len(fr) else 1.0,
                         "hit": False, "label": f"TP{t['n']}"} for i, t in enumerate(targets)],
            "openedAt": int(time.time() * 1000),
            "riskUsd": round(risk_usd, 2),
            "score": analysis_meta.get("score") if analysis_meta else None,
            "confidence": analysis_meta.get("confidence") if analysis_meta else None,
            "note": analysis_meta.get("note") if analysis_meta else "",
        }
        s["cash"] -= notional
        s["positions"].append(pos)
        _save(s)
        return {"ok": True, "position": pos,
                "riskBlocked": False}


def close_position(position_id: str, price: float | None = None,
                   reason: str = "manual") -> dict:
    with _lock:
        s = _load()
        pos = next((p for p in s["positions"] if p["id"] == position_id), None)
        if not pos:
            return {"ok": False, "error": "position not found"}
        px = float(price or pos["mark"])
        closed = _settle(s, pos, px, reason)
        _save(s)
        return {"ok": True, "closed": closed}


def _settle(s: dict, pos: dict, price: float, reason: str) -> dict:
    proceeds = pos["qty"] * price
    cost = pos["qty"] * pos["entry"]
    fee = (proceeds + cost) * config.load_settings().get("fee_pct", 0.1) / 100.0
    pnl = proceeds - cost - fee
    s["cash"] += proceeds
    s["positions"].remove(pos)
    day = time.strftime("%Y-%m-%d", time.gmtime())
    closed_pnl = round(pnl, 4)
    trade = {
        "id": uuid.uuid4().hex[:10],
        "positionId": pos["id"],
        "symbol": pos["symbol"],
        "entry": pos["entry"], "exit": price,
        "qty": pos["qty"], "pnl": round(pnl, 2),
        "pct": round((price / pos["entry"] - 1) * 100, 3),
        "reason": reason, "openedAt": pos["openedAt"],
        "closedAt": int(time.time() * 1000), "day": day,
        "riskUsd": pos.get("riskUsd"),
    }
    s["trades"].append(trade)
    snap = s.setdefault("snapshots", {}).setdefault(day, {"pnl": 0.0, "trades": 0})
    snap["pnl"] = round(snap["pnl"] + pnl, 2)
    snap["trades"] += 1
    eq_now = s["cash"] + sum(p["qty"] * p["mark"] for p in s["positions"])
    s["equityCurve"].append({"t": int(time.time() * 1000),
                             "equity": round(eq_now, 2)})
    s["equityCurve"] = s["equityCurve"][-500:]
    s["trades"] = s["trades"][-500:]
    risk.record_pnl(pnl, trades=1)
    risk.add_history_day(day, pnl)
    return trade


def mark_and_manage(prices: dict[str, float], candles: dict[str, list[dict]] | None = None) -> list[dict]:
    """Update marks; fire SL / TP exits conservatively (SL wins ties)."""
    events = []
    with _lock:
        s = _load()
        st = config.load_settings()
        for pos in list(s["positions"]):
            px = prices.get(pos["symbol"], pos["mark"])
            kls = (candles or {}).get(pos["symbol"])
            low = high = None
            if kls:
                window = kls[-2:] if len(kls) >= 2 else kls
                low = min(c["low"] for c in window)
                high = max(c["high"] for c in window)
            pos["mark"] = px

            # STOP LOSS first (conservative)
            breach = pos["stop"] if (low is not None and low <= pos["stop"]) else None
            if breach is None and px <= pos["stop"]:
                breach = px
            if breach:
                closed = _settle(s, pos, min(breach, px), "stop-loss")
                events.append({"type": "stop_loss", "trade": closed})
                continue

            # take-profit ladder with partial fills
            for t in pos["targets"]:
                if t["hit"]:
                    continue
                hit = (high is not None and high >= t["price"]) or px >= t["price"]
                if not hit:
                    break  # ladder order: later TPs only after earlier ones
                frac = t.get("fraction", 1.0)
                qty_part = pos["qty"] * frac
                proceeds = qty_part * t["price"]
                cost = qty_part * pos["entry"]
                fee = (proceeds + cost) * st.get("fee_pct", 0.1) / 100.0
                pnl = proceeds - cost - fee
                s["cash"] += proceeds
                pos["qty"] = round(pos["qty"] - qty_part, 8)
                t["hit"] = True
                t["at"] = int(time.time() * 1000)
                day = time.strftime("%Y-%m-%d", time.gmtime())
                s.setdefault("snapshots", {}).setdefault(day, {"pnl": 0.0, "trades": 0})
                snap = s["snapshots"][day]
                snap["pnl"] = round(snap["pnl"] + pnl, 2)
                snap["trades"] += 1
                s["trades"].append({
                    "id": uuid.uuid4().hex[:10], "positionId": pos["id"],
                    "symbol": pos["symbol"], "entry": pos["entry"],
                    "exit": t["price"], "qty": round(qty_part, 8),
                    "pnl": round(pnl, 2),
                    "pct": round((t["price"] / pos["entry"] - 1) * 100, 3),
                    "reason": f"partial {t['label']}",
                    "openedAt": pos["openedAt"],
                    "closedAt": int(time.time() * 1000), "day": day,
                    "riskUsd": pos.get("riskUsd"),
                })
                risk.record_pnl(pnl, trades=1)
                risk.add_history_day(day, pnl)
                events.append({"type": "take_profit", "label": t["label"],
                               "pnl": round(pnl, 2), "symbol": pos["symbol"]})
                if pos["qty"] <= 1e-9:
                    s["positions"].remove(pos)
                    break

        # mark-to-market equity curve (throttled to once/min)
        eq_now = s["cash"] + sum(p["qty"] * p["mark"] for p in s["positions"])
        now = int(time.time() * 1000)
        if not s["equityCurve"] or now - s["equityCurve"][-1]["t"] > 60_000:
            s["equityCurve"].append({"t": now, "equity": round(eq_now, 2)})
            s["equityCurve"] = s["equityCurve"][-500:]
        _save(s)
    return events


def status(prices: dict[str, float] | None = None) -> dict:
    with _lock:
        s = _load()
        if prices:
            for p in s["positions"]:
                if p["symbol"] in prices:
                    p["mark"] = prices[p["symbol"]]
        eq = s["cash"] + sum(p["qty"] * p["mark"] for p in s["positions"])
        st = config.load_settings()
        open_risk = sum(p.get("riskUsd", 0) for p in s["positions"])
        trades = s["trades"]
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        gross_w = sum(t["pnl"] for t in wins)
        gross_l = abs(sum(t["pnl"] for t in losses))
        day = time.strftime("%Y-%m-%d", time.gmtime())
        snap = s.get("snapshots", {}).get(day, {"pnl": 0.0, "trades": 0})
        return {
            "mode": st["trading_mode"],
            "cash": round(s["cash"], 2),
            "startEquity": s["startEquity"],
            "equity": round(eq, 2),
            "unrealized": round(eq - s["cash"] - sum(p["qty"] * p["entry"] for p in s["positions"]), 2),
            "openPositions": [
                {**p,
                 "value": round(p["qty"] * p["mark"], 2),
                 "upnl": round(p["qty"] * (p["mark"] - p["entry"]), 2),
                 "upnlPct": round((p["mark"] / p["entry"] - 1) * 100, 3),
                 "riskUsd": round(p.get("riskUsd", 0), 2)}
                for p in s["positions"]],
            "openRiskUsd": round(open_risk, 2),
            "trades": trades[-100:][::-1],
            "stats": {
                "totalTrades": len(trades),
                "wins": len(wins), "losses": len(losses),
                "winRate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
                "grossWin": round(gross_w, 2),
                "grossLoss": round(gross_l, 2),
                "profitFactor": round(gross_w / gross_l, 2) if gross_l else None,
                "netPnl": round(s["cash"] + sum(p["qty"] * p["mark"] for p in s["positions"])
                                - s["startEquity"], 2),
                "returnPct": round((eq / s["startEquity"] - 1) * 100, 3),
                "dayPnl": snap["pnl"], "dayTrades": snap["trades"],
            },
            "equityCurve": s["equityCurve"],
        }
