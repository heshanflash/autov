# 👩‍💻 AutoV Trader — The Team

මේ app එක "one-file script" එකක් නෙවෙයි — requirement එක හැම පැත්තකින්ම cover වෙන්න **7-role full team** එකක් විදිහට structure කරලා තියෙනවා.

## Roles & ownership

| Role | Owner | What they own |
|---|---|---|
| 📋 Product Manager | AutoV PM | Your brief → scope: whole-market scan, per-coin entry/SL/TP plans, $1000 account, **1% daily + 1% monthly loss caps**, day-by-day planning, reference research |
| 📊 Quant Analyst | Quant Desk | Composite scoring engine (EMA 9/21/50/200, RSI, MACD, Bollinger, ADX, Stochastic, volume, candle patterns → −100..+100), ATR stop-losses, R-multiple TP ladder with partial exits |
| 🛡️ Risk Manager | Risk Guard | 1%/day and 1%/month kill switches, 0.5% risk/trade, max 5 positions, 25% per-coin cap, budget check before *every* entry, persistent counters |
| ⚙️ Backend | API Team | Binance REST (public + signed), live→demo data fallback, thread-pooled scanner, paper ledger, planner, backtester |
| 🎨 Frontend | UI Team | Trading-desk dashboard: regime cards, scanner, lightweight-charts with entry/SL/TP lines, risk gauges, planner, portfolio, backtest |
| 🔭 Research | Reference Desk | Benchmarked 3Commas / Pionex / Cryptohopper / Bitsgap / open-source bots — see [REFERENCES.md](REFERENCES.md) |
| 🧪 QA | QA Team | Risk-gate edge cases, partial-TP math, conservative SL-first backtest fills, API contract checks |

## Sprint history

1. **Sprint 1 — Foundation**: config/.env secrets, Binance client with offline demo fallback, indicator library
2. **Sprint 2 — Brain**: analyzer scoring + trade plan builder, market regime engine
3. **Sprint 3 — Safety**: risk manager with daily/monthly halt, position sizing, persistent state
4. **Sprint 4 — Execution**: paper portfolio (partial TP ladder, SL management), live-order path (gated)
5. **Sprint 5 — Product**: full dashboard UI, day planner, backtester, scanner UX
6. **Sprint 6 — Research**: reference analysis + adoption of their safety patterns

## Non-negotiables the team enforced

- Paper mode default — live orders require an explicit setting change + confirmation
- API keys live only in `.env` (git-ignored), trading permission only, withdrawals off
- Every entry carries a stop-loss; SL checks bypass everything else
- No new risk once the daily or monthly 1% budget is spent
