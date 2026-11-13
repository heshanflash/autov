# 🔭 Reference Apps — Research & What We Borrowed

ඔයා කිව්ව "මෙව්වා වගේ apps තියෙනවා නම් reference කරලා analyze කරන්න" — ඒ අනුව 2026 දී top automated-crypto-trading platforms සහ open-source Binance bots ප්‍රධාන කීපයක් හදාරලා, ඒවායේ **strongest safety & analysis patterns** මේ app එකට ගෙනාවා.

## 1. 3Commas — closest commercial twin
Mature multi-exchange bot platform (est. 2017): DCA bots, grid bots, and signal bots fed by TradingView webhooks, plus a SmartTrade terminal for complex stop-loss / take-profit orders and a $10,000 virtual demo account [1]. Paid plans run $20–140/month [1].
**අපේ version:** same signal→plan→auto-execute flow, but $0/month, and every plan always shows entry + SL + TP1/2/3 *before* you can take it.

## 2. Pionex — safety by architecture
Exchange with 16+ built-in bots (grid, reverse grid, DCA, arbitrage); no third-party API keys needed because funds never leave the venue; 0.05% spot fee and no bot subscription [2].
**අපේ version:** keys never leave your machine (`.env`, git-ignored), paper mode is the default so the safest path needs *no* keys at all.

## 3. Cryptohopper — indicator strategies + paper gate
Indicator strategy designer, signal marketplace and paper trading (one paper bot per tier), with a "panic button" that closes everything [3][4]. $29–129/month [3].
**අපේ version:** built-in indicator strategy engine (the analyzer), paper-first workflow, one-click **close** on every position.

## 4. Bitsgap — backtesting & demo capital
Grid/DCA/futures bots across 17 exchanges, $100,000 demo balance, backtests per plan tier, AI assistant that proposes bot configurations; rejects API keys that have withdrawal rights enabled [1][5].
**අපේ version:** Backtest tab runs the *same* analyzer + SL/TP rules on history; Settings screen documents "trading-only, no-withdrawal" key hygiene.

## 5. Open-source Binance bots — operational discipline
Popular GitHub bots show the operational playbook: ordered risk checks (allowlist → size cap → per-symbol cap → total exposure → **daily-loss halt** → cooldown), dry-run mode, and exits that never wait for confirmation [6]. The well-known volatility bot scans every USDT pair for momentum spikes with trailing SL/TP [7].
**අපේ version:** the scanner covers the whole USDT universe, `can_open()` runs the same ordered risk chain on every entry, and paper/live both default to mechanical SL handling.

## 6. AI multi-agent bots — confidence gating
Newer bots require an AI committee to *approve* entries at a confidence threshold while stop-loss exits stay 100% mechanical, and ignore signals that don't cover round-trip fees [8].
**අපේ version:** every signal carries a confidence %, entries under score threshold are "WEAK" (plan shown, human decides), exits are mechanical, and fee math (0.1% taker/side) is inside every PnL and backtest.

## Feature matrix (yours vs. the field)

| Feature | AutoV Trader | 3Commas | Pionex | Cryptohopper | Bitsgap |
|---|---|---|---|---|---|
| Whole-market per-coin analysis | ✅ | via signals | ❌ | partial | ❌ |
| Entry + SL + TP plan shown before trade | ✅ | ✅ | ✅ | ✅ | ✅ |
| $1000 account, 1% daily & monthly loss kill-switch | ✅ built-in | custom | ❌ | partial | ❌ |
| Day-by-day planner | ✅ | ❌ | ❌ | ❌ | ❌ |
| Backtest on same logic | ✅ | paid tiers | grid only | paid tiers | paid tiers |
| Paper mode default | ✅ | demo acct | demo excludes bots | 1 paper bot | $100k demo |
| Monthly fee | **$0** | $20–140 | 0.05% fee | $29–129 | $29–149 |

### Sources
- [1] Best crypto trading bots: features, costs & testing (2026) — https://www.turbinefi.com/blog/best-crypto-trading-bots
- [2] 7 best crypto trading bots 2026 — https://cryptotradingbots.info/best-crypto-trading-bots-2026-6
- [3] 8 best automated crypto trading platforms 2026 — https://cryptoadventure.com/8-best-automated-crypto-trading-platforms-in-2026/
- [4] Best AI crypto trading bots 2026 — https://www.gt-protocol.io/learn/best-ai-crypto-trading-bots-2026/
- [5] Best AI crypto trading bots 2026 (trade-only keys) — https://www.gt-protocol.io/learn/best-ai-crypto-trading-bots-2026/
- [6] TradingView webhook bot (risk checks / dry-run architecture) — https://github.com/78934720/tradingview-bot
- [7] Binance volatility trading bot (community write-up) — https://www.reddit.com/r/Python/comments/ndt8m6/
- [8] binance-bot (AI multi-agent approvals, fee-aware TP) — https://pkg.go.dev/github.com/wferreirauy/binance-bot
