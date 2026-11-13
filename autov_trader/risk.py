"""Risk manager - the guard rails around your $1000 account.

Hard rules (defaults match the brief):
  * max loss 1% in a single day  -> new entries blocked until next UTC day
  * max loss 1% in a calendar month -> new entries blocked until month rollover
  * per-trade risk 0.5% of equity
  * max 5 open positions, max 25% equity in one symbol
State persists to state/risk_state.json.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from . import config

STATE_FILE = config.STATE_DIR / "risk_state.json"
_lock = threading.RLock()


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _month() -> str:
    return time.strftime("%Y-%m", time.gmtime())


def _load() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"realized_pnl": {}, "daily_reset": None, "month_reset": None,
            "halted_until": None, "halt_reason": None}


def _save(s: dict) -> None:
    config.STATE_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def reset_day_month(s: dict) -> dict:
    today, month = _today(), _month()
    if s.get("daily_reset") != today:
        # new UTC day: roll yesterday's pnl out of the daily window
        s["daily_reset"] = today
        s["day_pnl"] = 0.0
        s["day_trades"] = 0
        s["halted_until"] = None
        s["halt_reason"] = None
    if s.get("month_reset") != month:
        s["month_reset"] = month
        s["month_pnl"] = 0.0
        s["month_trades"] = 0
        s["halted_until"] = None
        s["halt_reason"] = None
    s.setdefault("day_pnl", 0.0)
    s.setdefault("month_pnl", 0.0)
    s.setdefault("day_trades", 0)
    s.setdefault("month_trades", 0)
    return s


def snapshot() -> dict:
    with _lock:
        s = reset_day_month(_load())
        _save(s)
        st = config.load_settings()
        equity = st["account_size"] + s["month_pnl"]
        day_budget = equity * st["daily_max_loss_pct"] / 100.0
        month_budget = equity * st["monthly_max_loss_pct"] / 100.0
        day_used = max(0.0, -s["day_pnl"])
        month_used = max(0.0, -s["month_pnl"])
        blocked = s.get("halt_reason") is not None
        return {
            "date": s["daily_reset"], "month": s["month_reset"],
            "dayPnl": round(s["day_pnl"], 2),
            "dayTrades": s["day_trades"],
            "monthPnl": round(s["month_pnl"], 2),
            "monthTrades": s["month_trades"],
            "dailyBudgetUsd": round(day_budget, 2),
            "dailyUsedUsd": round(day_used, 2),
            "dailyRemainingUsd": round(max(0.0, day_budget - day_used), 2),
            "dailyLimitPct": st["daily_max_loss_pct"],
            "monthlyBudgetUsd": round(month_budget, 2),
            "monthlyUsedUsd": round(month_used, 2),
            "monthlyRemainingUsd": round(max(0.0, month_budget - month_used), 2),
            "monthlyLimitPct": st["monthly_max_loss_pct"],
            "riskPerTradeUsd": round(equity * st["risk_per_trade_pct"] / 100.0, 2),
            "halted": blocked,
            "haltReason": s.get("halt_reason"),
            "tradingMode": st["trading_mode"],
        }


def can_open(risk_usd: float, open_positions: int, symbol_exposure_pct: float
             ) -> tuple[bool, str]:
    """Gate every new entry. Returns (allowed, reason-if-blocked)."""
    with _lock:
        s = reset_day_month(_load())
        st = config.load_settings()
        equity = st["account_size"] + s["month_pnl"]

        if s.get("halt_reason"):
            _save(s)
            return False, f"halted: {s['halt_reason']}"

        day_budget = equity * st["daily_max_loss_pct"] / 100.0
        if max(0.0, -s["day_pnl"]) >= day_budget:
            s["halt_reason"] = (f"daily loss limit "
                                f"{st['daily_max_loss_pct']}% reached "
                                f"(day PnL {s['day_pnl']:.2f} USD) — resumes next UTC day")
            _save(s)
            return False, s["halt_reason"]

        month_budget = equity * st["monthly_max_loss_pct"] / 100.0
        if max(0.0, -s["month_pnl"]) >= month_budget:
            s["halt_reason"] = (f"monthly loss limit "
                                f"{st['monthly_max_loss_pct']}% reached "
                                f"(month PnL {s['month_pnl']:.2f} USD) — "
                                f"resets on month rollover")
            _save(s)
            return False, s["halt_reason"]

        if open_positions >= st["max_open_positions"]:
            _save(s)
            return False, f"max open positions reached ({st['max_open_positions']})"

        if symbol_exposure_pct > st["max_per_symbol_pct"]:
            _save(s)
            return False, (f"per-symbol exposure {symbol_exposure_pct:.1f}% "
                           f"exceeds cap {st['max_per_symbol_pct']}%")

        if risk_usd > day_budget - max(0.0, -s["day_pnl"]):
            _save(s)
            return False, (f"risk {risk_usd:.2f} USD would exceed today's "
                           f"remaining loss budget {day_budget - max(0.0, -s['day_pnl']):.2f} USD")

        _save(s)
        return True, "ok"


def record_pnl(pnl: float, trades: int = 0) -> None:
    with _lock:
        s = reset_day_month(_load())
        s["day_pnl"] = s.get("day_pnl", 0.0) + pnl
        s["month_pnl"] = s.get("month_pnl", 0.0) + pnl
        s["day_trades"] = s.get("day_trades", 0) + trades
        s["month_trades"] = s.get("month_trades", 0) + trades
        st = config.load_settings()
        equity = st["account_size"] + s["month_pnl"]
        # evaluate halt immediately after the loss
        day_budget = equity * st["daily_max_loss_pct"] / 100.0
        month_budget = equity * st["monthly_max_loss_pct"] / 100.0
        if max(0.0, -s["day_pnl"]) >= day_budget:
            s["halt_reason"] = f"daily {st['daily_max_loss_pct']}% loss limit hit"
        elif max(0.0, -s["month_pnl"]) >= month_budget:
            s["halt_reason"] = f"monthly {st['monthly_max_loss_pct']}% loss limit hit"
        _save(s)


def risk_state_daily_history(days: int = 30) -> list[dict]:
    """Day-by-day planning history derived from the pnl ledger."""
    with _lock:
        s = reset_day_month(_load())
        _save(s)
        hist: dict[str, float] = dict(s.get("realized_pnl", {}))
    out = []
    import datetime as dt
    today = dt.datetime.utcnow().date()
    for i in range(days - 1, -1, -1):
        d = (today - dt.timedelta(days=i)).isoformat()
        pnl = hist.get(d, s.get("day_pnl", 0.0) if d == s["daily_reset"] else 0.0)
        out.append({"date": d, "pnl": round(pnl, 2)})
    return out


def add_history_day(date_iso: str, pnl: float) -> None:
    with _lock:
        s = _load()
        h = s.setdefault("realized_pnl", {})
        h[date_iso] = round(h.get(date_iso, 0.0) + pnl, 4)
        # keep 180 days
        for old in sorted(h)[:-180]:
            h.pop(old, None)
        _save(s)


def reset_all(account_size: float | None = None) -> dict:
    """Factory reset risk counters (used by 'reset paper account')."""
    with _lock:
        config.STATE_DIR.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps({
            "realized_pnl": {}, "day_pnl": 0.0, "month_pnl": 0.0,
            "day_trades": 0, "month_trades": 0,
            "daily_reset": None, "month_reset": None,
            "halted_until": None, "halt_reason": None}, indent=2), encoding="utf-8")
        if account_size:
            config.save_settings({"account_size": float(account_size)})
    return snapshot()
