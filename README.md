# AutoV — Auto Visitor Blog & **AutoV Trader** 📈

## 🤖 NEW: AutoV Trader — Binance chart-analysis & risk-managed trading desk

Every coin → chart analysis → market analysis → **Entry / Stop-Loss / Take-Profit plan**
on a **$1000 account** with **max 1% loss per day & per month** (auto-halt), day-by-day planning,
paper mode by default, live Binance orders optional.

### Quick start
```bash
git clone <this repo>
cd autov
cp .env.example .env        # add your Binance API keys + risk settings
./run.sh                    # → http://localhost:5000
```

### What's inside
| Tab | What it does |
|---|---|
| **Dashboard** | Market regime (RISK-ON/OFF), breadth, BTC trend, risk gauges, top signals, equity curve |
| **Scanner** | Whole USDT market scored (EMA/RSI/MACD/BB/ADX/Stochastic/volume/patterns) with entry, SL, TP per coin |
| **Charts** | Candles + EMA9/21/50 + entry/SL/TP price lines, analysis checks, one-click trade |
| **Day Plan** | 1% daily budget, 1% monthly budget, trades-left calculator, 30-day history |
| **Portfolio** | $1000 paper ledger: open positions with uPnL, TP ladder, close button, stats |
| **Backtest** | Same strategy on historical candles: win rate, profit factor, max DD |
| **Team & References** | The 7-role team behind the build + analyzed reference apps (3Commas, Pionex, Cryptohopper, Bitsgap...) |

### Safety rules (defaults, all editable in ⚙ Settings)
- **Daily loss cap 1%** → new entries blocked until next UTC day
- **Monthly loss cap 1%** → blocked until month rollover
- **0.5% risk per trade**, max **5** open positions, max **25%** equity per coin
- Every entry carries a stop-loss; TP ladder TP1/TP2/TP3 (partial exits)
- **Paper mode default** — live mode needs explicit confirmation
- API keys only in `.env` (git-ignored) — use **trading-only keys, withdrawals disabled**

> ⚠️ Crypto trading involves risk of loss. This is a decision-support tool, not financial advice.

**Docs:** [docs/TEAM.md](docs/TEAM.md) · [docs/REFERENCES.md](docs/REFERENCES.md)

---

## 📁 Original project: Auto Visitor Blog (Custom Refferer)
<br>
<img src="https://i.screenshot.net/l049dtj">
<br><br>
<img src="https://i.screenshot.net/pjmvyc2">
<br><br>
<img src="https://i.screenshot.net/4w3evud">
<br>

<pre>
$ apt update && apt upgrade
$ pkg install php
$ pkg install git
$ git clone https://github.com/underxploit/Autov
$ cd Autov
$ php auto.php
</pre>
