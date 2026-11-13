"""AutoV Trader web server - API + dashboard.

Run:  .venv/bin/python server.py      (binds 0.0.0.0:5000)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from autov_trader import (analyzer, backtest, binance_client, config,
                          portfolio, risk, scanner)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("autov.server")

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = Flask(__name__, static_folder=None)


# --------------------------- UI ---------------------------
@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:path>")
def static_files(path: str):
    return send_from_directory(STATIC, path)


# --------------------------- status / settings ---------------------------
@app.get("/api/status")
def api_status():
    st = config.load_settings()
    snap = risk.snapshot()
    keys_set = bool(config.API_KEY and config.API_SECRET)
    bal = None
    if st["trading_mode"] == "live" and keys_set:
        bal = binance_client.client.account_balance_usdt()
    return jsonify({
        "app": "AutoV Trader",
        "version": "1.0.0",
        "tradingMode": st["trading_mode"],
        "dataSource": binance_client.client.data_source,
        "liveData": binance_client.client.live_data,
        "apiKeysConfigured": keys_set,
        "binanceBalanceUsdt": bal,
        "settings": {k: st[k] for k in st},
        "risk": snap,
        "equity": portfolio.status()["equity"],
        "disclaimer": ("Paper mode simulates every trade locally. Live mode "
                       "sends real Binance spot orders — use dedicated "
                       "trade-only API keys with withdrawals disabled."),
    })


@app.get("/api/settings")
def get_settings():
    return jsonify(config.load_settings())


@app.post("/api/settings")
def post_settings():
    body = request.get_json(force=True, silent=True) or {}
    allowed = {}
    numeric = {"account_size", "risk_per_trade_pct", "daily_max_loss_pct",
               "monthly_max_loss_pct", "max_open_positions",
               "max_per_symbol_pct", "atr_sl_mult", "scan_limit",
               "min_quote_volume", "fee_pct"}
    choices = {"trading_mode": {"paper", "live"},
               "data_mode": {"auto", "live", "demo"},
               "timeframe": set(analyzer.VALID_TFS)}
    for k, v in body.items():
        if k not in config.DEFAULTS:
            continue
        if k in numeric:
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if k in ("max_open_positions", "scan_limit"):
                v = int(v)
        if k in choices and v not in choices[k]:
            continue
        if k in ("rr_targets", "tp_fractions") and isinstance(v, list):
            v = [float(x) for x in v]
        allowed[k] = v
    st = config.save_settings(allowed)
    if "account_size" in allowed:
        # keep paper ledger in sync when the user changes capital
        pass
    return jsonify(st)


# --------------------------- market / scan ---------------------------
@app.get("/api/scan")
def api_scan():
    force = request.args.get("force") in ("1", "true", "yes")
    tf = request.args.get("tf")
    data = scanner.run_scan(force=force, timeframe=tf)
    data["stats"] = scanner.scan_stats(data)
    return jsonify(data)


@app.get("/api/symbol/<symbol>")
def api_symbol(symbol: str):
    symbol = symbol.upper()
    st = config.load_settings()
    tf = request.args.get("tf", st["timeframe"])
    if tf not in analyzer.VALID_TFS:
        tf = "1h"
    kls = binance_client.client.get_klines(symbol, tf, 300)
    a = analyzer.analyze_candles(
        kls, st, st["account_size"] + risk.snapshot()["monthPnl"])
    a.update({"symbol": symbol, "tf": tf,
              "dataSource": binance_client.client.data_source,
              "candles": kls})
    return jsonify(a)


# --------------------------- portfolio / planner ---------------------------
@app.get("/api/portfolio")
def api_portfolio():
    prices = {}
    for p in portfolio.status()["openPositions"]:
        prices[p["symbol"]] = p["mark"]
    st = config.load_settings()
    if binance_client.client.live_data:
        try:
            tick = {t["symbol"]: t["lastPrice"]
                    for t in binance_client.client.get_tickers()}
            prices = {s: tick.get(s, v) for s, v in prices.items()}
        except Exception:  # noqa: BLE001
            pass
    return jsonify({**portfolio.status(prices),
                    "risk": risk.snapshot(),
                    "settings": st,
                    "binanceBalanceUsdt": (binance_client.client.account_balance_usdt()
                                           if st["trading_mode"] == "live"
                                           else None)})


@app.post("/api/portfolio/positions")
def api_open_position():
    body = request.get_json(force=True, silent=True) or {}
    symbol = (body.get("symbol") or "").upper()
    plan = body.get("plan") or {}
    price = float(body.get("price") or plan.get("entry") or 0)
    if not symbol or not price:
        return jsonify({"ok": False, "error": "symbol and price required"}), 400
    res = portfolio.open_position(symbol, plan, price,
                                  {"score": body.get("score"),
                                   "confidence": body.get("confidence")})
    status_code = 200 if res.get("ok") else 409

    # Live mode: try to mirror the paper position on Binance
    if res.get("ok") and config.load_settings()["trading_mode"] == "live":
        try:
            order = binance_client.client.market_buy(
                symbol, res["position"]["qty"] * res["position"]["entry"])
            res["liveOrder"] = order
            try:
                binance_client.client.place_exit_orders(
                    symbol, res["position"]["qty"],
                    res["position"]["targets"][0]["price"],
                    res["position"]["stop"])
            except Exception as e:  # noqa: BLE001
                res["liveExitWarning"] = f"TP/SL order failed: {e}"
        except Exception as e:  # noqa: BLE001
            res["liveError"] = str(e)
    return jsonify(res), status_code


@app.post("/api/portfolio/close")
def api_close_position():
    body = request.get_json(force=True, silent=True) or {}
    pid = body.get("positionId")
    st = config.load_settings()
    prices = {}
    if binance_client.client.live_data:
        try:
            prices = {t["symbol"]: t["lastPrice"]
                      for t in binance_client.client.get_tickers()}
        except Exception:  # noqa: BLE001
            pass
    pos = next((p for p in portfolio.status()["openPositions"]
                if p["id"] == pid), None)
    px = prices.get(pos["symbol"], pos["mark"]) if pos else None
    res = portfolio.close_position(pid, px, "manual close")
    if res.get("ok") and st["trading_mode"] == "live" and pos:
        try:
            binance_client.client.cancel_open_orders(pos["symbol"])
        except Exception as e:  # noqa: BLE001
            res["liveWarning"] = str(e)
    status_code = 200 if res.get("ok") else 404
    return jsonify(res), status_code


@app.post("/api/portfolio/reset")
def api_reset():
    body = request.get_json(force=True, silent=True) or {}
    return jsonify(portfolio.reset(body.get("accountSize")))


@app.get("/api/planner")
def api_planner():
    """Day-by-day plan + history for the $1000 account."""
    st = config.load_settings()
    snap = risk.snapshot()
    hist = risk.risk_state_daily_history(30)
    port = portfolio.status()
    day_budget = snap["dailyBudgetUsd"]
    month_budget = snap["monthlyBudgetUsd"]

    # forward plan: with the current rules, how many trades fit today
    risk_per = snap["riskPerTradeUsd"]
    trades_left_today = (snap["dailyRemainingUsd"] / risk_per
                         if risk_per > 0 else 0)
    plans = []
    for h in hist:
        plans.append({
            **h,
            "budget": round(day_budget, 2),
            "withinBudget": h["pnl"] >= -day_budget,
            "trades": (snap["dayTrades"] if h["date"] == snap["date"] else 0),
        })
    return jsonify({
        "settings": {k: st[k] for k in
                     ("account_size", "risk_per_trade_pct",
                      "daily_max_loss_pct", "monthly_max_loss_pct",
                      "max_open_positions")},
        "risk": snap,
        "history": plans[::-1],
        "today": {
            "date": snap["date"],
            "pnl": snap["dayPnl"],
            "trades": snap["dayTrades"],
            "budgetUsd": round(day_budget, 2),
            "remainingUsd": snap["dailyRemainingUsd"],
            "tradesLeft": int(trades_left_today),
            "suggestedRiskUsd": round(risk_per, 2),
        },
        "month": {
            "label": snap["month"],
            "pnl": snap["monthPnl"],
            "trades": snap["monthTrades"],
            "budgetUsd": round(month_budget, 2),
            "remainingUsd": snap["monthlyRemainingUsd"],
            "usedPct": round(snap["monthlyUsedUsd"] / month_budget * 100, 1)
                       if month_budget else 0,
        },
        "openRiskUsd": port["openRiskUsd"],
        "openPositions": len(port["openPositions"]),
    })


# --------------------------- backtest ---------------------------
@app.post("/api/backtest")
def api_backtest():
    body = request.get_json(force=True, silent=True) or {}
    symbol = (body.get("symbol") or "BTCUSDT").upper()
    tf = body.get("timeframe", "1h")
    limit = min(int(body.get("limit", 700)), 1000)
    if tf not in analyzer.VALID_TFS:
        tf = "1h"
    return jsonify(backtest.run_backtest(symbol, tf, limit))


# --------------------------- team / references ---------------------------
@app.get("/api/references")
def api_references():
    p = ROOT / "docs" / "REFERENCES.json"
    if p.exists():
        return jsonify(json.loads(p.read_text(encoding="utf-8")))
    return jsonify([])


@app.get("/api/team")
def api_team():
    p = ROOT / "docs" / "TEAM.json"
    if p.exists():
        return jsonify(json.loads(p.read_text(encoding="utf-8")))
    return jsonify([])


@app.get("/api/health")
def api_health():
    return jsonify({"ok": True, "ts": int(__import__("time").time())})


if __name__ == "__main__":
    port = int(__import__("os").environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
