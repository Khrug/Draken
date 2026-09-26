# Safety / risk audit — 2026-09-26

Scope: every file in the repo (configs, compose, runners, evaluate/experiments, cockpit, logs,
backtest outputs, `.env` key *names* only). Freqtrade version verified from the running
containers: **2026.8** (`freqtradeorg/freqtrade:stable`). Freqtrade semantics below were checked
against the installed source inside `draken-trend` and the stable docs (context7), not from memory.

Status: dry-run only. No API keys present. Nothing in this audit changes that.

---

## 1. Findings, ranked by severity

### HIGH

**H1. The "5 % daily loss cap" did not work as the comment claimed** (`common_risk.py`) — *fixed*
- `MaxDrawdown` had `trade_limit: 5`: it only evaluates if **5 closed trades** fall inside the
  24 h window. The strategies close ~0.1–0.5 trades/day per bot (Breakout 1h: 136 trades in 273
  days), so it would essentially never evaluate.
- No `calculation_mode` → default `"ratios"` (confirmed in source): it sums per-trade profit
  ratios, not % of account. With ~50 % stakes, a "5 %" ratio drawdown ≈ 2.5 % of account.
- Even when it fires it is only an **entry lock**: it looks at closed trades only, ignores
  unrealised losses, and never closes open positions. It is a rolling 24 h window, not a
  calendar day.
- Fix: `calculation_mode: "equity"` (real % of account, starting balance + prior profit),
  `trade_limit: 1`. Comment rewritten to say what it actually does ("soft cap on new entries").
  Verified it loads in 2026.8 (`ProtectionManager` constructs it with mode `equity`, limit 1).

**H2. No stop protection if the bot is down** (config, tech lead)
- No `order_types` / `stoploss_on_exchange`. The −3 % stop lives only inside the bot (a market
  sell issued by the bot loop). If the Windows PC sleeps, Docker restarts, or the network drops,
  open positions have **no stop at all**. Bitvavo has no stoploss-on-exchange support in
  Freqtrade 2026.8 (and is not an officially supported exchange); OKX, Binance and Bybit do.
- The cockpit "stop" button stops the bot but leaves open positions unmanaged — it is not a
  kill switch.

**H3. Three bots, one wallet assumption** (config, tech lead)
- Each bot runs `stake_amount: "unlimited"` against its own 90 EUR dry-run wallet (270 EUR
  simulated in total). Live on one 90 EUR account, each bot would size against the *shared*
  balance and none of the protections (StoplossGuard, MaxDrawdown) see the other bots' losses.
  Account-level daily risk would be up to ~3× the per-bot numbers below.

### MEDIUM

**M1. The backtests are frictionless on exits.** Stops fill exactly at −3 % (backtest avg
stop exit −3.48 % = 3 % + 0.5 % round-trip fee). No slippage is modelled. With a 0.25 % taker
fee each side, the round trip costs 0.5 %: 10 % of a 5 % ROI target and 17 % of the 3 % stop.

**M2. The two "PASS" results are not evidence of edge.** Breakout 1h: IS −37 %, full period
−27.4 % vs hold −27.7 % (bitvavo) — a 0.3 pp margin. Profit factor IS 0.53, 13 consecutive
losses. The OOS window was a +64 % market. Treat as "no better than holding", not "works".

**M3. Protections trigger on stop-loss exits only.** StoplossGuard counts `stop_loss` exits;
`exit_signal` losses (Breakout IS: 76 losing signal exits, avg −1.14 %) never count toward it.

### LOW

**L1. `startup_candle_count` too small** — *fixed*
- BreakoutDonchian: `atr_mean` = 50-candle mean of ATR14, shifted 1 → needs ≥ 65 candles; had 50.
  Effect was NaN (no signal) for the first ~15 backtest candles, not false signals. Now 100.
- TrendEmaAdx: EMA55 and ADX14 are recursive; with 100 candles the EMA55 seed still carries
  ~19 % weight, so early-window backtest crossings differ from live. Now 200. (Can be confirmed
  with `freqtrade recursive-analysis`.)
- MeanRevBbRsi (50: BB20 exact, RSI14 residual <10 %), DrakenGamma (1500), MomentumRotation
  (490), FreqAIRegime (240): acceptable.

**L2. CooldownPeriod 25 min is a no-op on 30m and 1h** (shorter than one candle). Only affects
15m. Comment updated; value left unchanged (it is a registered parameter).

**L3. MomentumRotation** will raise if BTC/EUR data is missing (`btc` is None); fine while BTC/EUR
is in the whitelist.

### Checked and clean

- **Lookahead:** none found. All signals use closed-candle values; Freqtrade fills at the *next*
  candle's open in backtest and on the new candle live, so using `close` in the signal is correct.
  Breakout shifts its channel by 1 so the current candle cannot define its own breakout.
  DrakenGamma uses `@informative` (merged only after the higher TF candle closes). FreqAIRegime's
  target uses `shift(-n)` but only as the training label (mean of the next 24 closes — verified
  arithmetic). MomentumRotation aligns all coins by timestamp; each row uses only same-time closes.
- **Repainting:** none. EMA/ADX/RSI/BB/ATR/Donchian on closed candles do not repaint.
- **Stoploss/trailing:** `stoploss = -0.03`, no trailing configured anywhere, ROI tables sensible
  (`{"0": 100}` = ROI disabled is intentional). ROI keys are minutes (MeanRev `"30"` = 30 min).
- **Protections location:** in 2026.8 protections must be defined via the strategy `protections`
  property (config-based protections were removed). All strategies do this, and the live logs show
  all three protections loaded. Backtests pass `--enable-protections` (both runners).

---

## 2. Position sizing (current config)

`stake_amount "unlimited"`, `max_open_trades 2`, `tradable_balance_ratio 0.99`, wallet 90 EUR:
stake = 90 × 0.99 / 2 = **44.55 EUR per trade (49.5 % of wallet)**; both slots = 99 % deployed.

| Case (per trade, 44.55 EUR stake, 0.25 %/side fee) | Loss EUR | % of wallet |
|---|---|---|
| Stop at −3 %, no slippage (what backtests assume) | 1.56 | 1.7 % |
| + 0.5 % slippage on the market stop | 1.78 | 2.0 % |
| + 1.5 % slippage (fast move / thin book) | 2.23 | 2.5 % |
| Bot offline during a −15 % move, no exchange stop | 6.9 | 7.7 % |

Per day, per bot: StoplossGuard locks after 3 stop-loss exits (~4.7–5.3 EUR ≈ 5–6 %); a trade
already open at lock time adds ~1.6–2.2 EUR, and signal-exit losses are not counted → realistic
ceiling **~6–8 % / day**. Worst single day in backtests: −3.9 EUR (Breakout 1h IS). Bot down
with both slots open during a −15 % crash: **~15 %** in one event. Three bots on one real
account: multiply by up to 3.

## 3. Exchange minimum order sizes (public market data, ccxt, 2026-09-26)

Freqtrade adds a reserve: min stake = exchange min × 1.05 / (1 − 0.03) ≈ × 1.08.

| Exchange | BTC/EUR | ETH/EUR | SOL/EUR | Effective Freqtrade min stake |
|---|---|---|---|---|
| Bitvavo | 5 EUR | 5 EUR | 5 EUR | ~5.4 EUR |
| OKX | 0.0001 BTC ≈ 7.4 EUR | 0.001 ETH ≈ 2.4 EUR | 0.01 SOL ≈ 1.1 EUR | BTC ~8.0 EUR |
| Binance | 5 EUR | 5 EUR | 5 EUR | ~5.4 EUR |
| Bybit | 1 EUR | 1 EUR | 1 EUR | ~1.1 EUR |
| Kraken | 0.45 EUR (+ amount min 0.00005 BTC ≈ 3.7 EUR) | | 0.06 SOL ≈ 6.4 EUR | ~4–7 EUR |

Current 44.55 EUR stakes are far above every minimum. Problems start only if the stake per
trade falls below ~8 EUR (OKX BTC): e.g. wallet < ~16 EUR with 2 slots, or ≥ 11 slots on 90 EUR.
MomentumRotation (3 slots ≈ 29.7 EUR) is fine for the majors; re-check per-alt `amount` minimums
if that universe is ever traded. The recommended 20 EUR fixed stake below clears all of these.

---

## 4. Recommendations for config (tech lead)

I did not edit `config.json` / compose. Suggested values:

1. `"stake_amount": 20` (fixed EUR), keep `"max_open_trades": 2` → max 40 EUR deployed (44 %),
   nominal stop loss per trade ≈ 0.70 EUR (0.8 %), ≈ 1.0 EUR with 1.5 % slippage. Re-run the
   backtest matrix with the same value so paper vs backtest stays comparable.
2. If more than one bot will ever share a real account: give each bot `"available_capital"`
   (e.g. 30 EUR each for three bots) instead of `"unlimited"`, so their sizing does not overlap.
3. `"order_types": {"entry": "limit", "exit": "limit", "stoploss": "market",
   "stoploss_on_exchange": true, "stoploss_on_exchange_interval": 60}` — requires an exchange that
   supports it in 2026.8 (OKX, Binance, Bybit yes; Bitvavo no). Weigh this in the exchange choice.
4. `"cancel_open_orders_on_exit": true`.
5. Stress backtest: rerun the survivors with fee + 0.1 %/side (e.g. `"fee": 0.0035` on a
   0.25 % exchange) as a crude slippage proxy. A strategy that only passes frictionless is out.
6. Restart the bots to pick up the `common_risk.py` change, and record it in RULES.md as an
   implementation correction (it changes backtest results, so the matrix and E1–E3 need a re-run).

---

## 5. Go-live gate (all must be true, checked by someone other than the author)

- [ ] Out-of-sample profit > 0 **after** realistic fees and the +0.1 %/side slippage stress run.
- [ ] ≥ 30 OOS trades (RULES v1) and max OOS drawdown < 15 %.
- [ ] Beats buy-and-hold in-sample and over the full period by a margin larger than fees on one
      round trip (RULES v2) — a 0.3 pp margin is not a pass in spirit.
- [ ] ≥ 4 weeks and ≥ 20 closed trades of dry-run (RULES.md; stricter than the 2-week minimum),
      with paper P&L, trade count and win rate inside the backtest's range for the same period.
- [ ] Fixed stake (not `unlimited`), `available_capital` per bot if sharing an account.
- [ ] Stop-loss on exchange enabled on an exchange that supports it, and tested in dry-run.
- [ ] Kill switch tested end to end: `stopentry` → `forceexit all` → `stop`, and the account shows
      no open orders or positions afterwards. The current cockpit "stop" alone does not do this.
- [ ] Trade-only API key, withdrawals disabled, IP-restricted; hard loss limit written down
      before the first trade (RULES.md).
- [ ] Start with the smallest stake the exchange accepts, not the full wallet.
- [ ] Going live is Kai's decision alone.

## 6. On doubling the money in 24 h

No configuration of this bot should be tuned toward that. Doubling in a day needs +100 %: at
these strategies' pace (≤ ~2 trades/day, +5 % ROI target) that is ~15 consecutive full-size wins
in one day, which cannot happen, so the only route is leverage or all-in bets — i.e. roughly a
coin flip that pays out 2× while fees and slippage push the odds below 50 %. Repeating a sub-50 %
double-or-nothing bet drives the probability of losing the whole wallet toward 1 (after five
attempts, P(still solvent) is at most 0.5^5 ≈ 3 %). The backtests show no measurable edge (profit factor 0.5–1.1,
full-period results at or below holding), and with zero edge the Kelly-optimal bet size is zero.
The realistic goal for this setup is to learn cheaply and lose little while doing it.

---

## Changes made (files owned by safety)

- `user_data/strategies/common_risk.py`: MaxDrawdown → `calculation_mode: "equity"`, `trade_limit: 1`;
  comments corrected (soft entry lock, not a hard daily cap; cooldown no-op on 30m/1h).
- `user_data/strategies/BreakoutDonchian.py`: `startup_candle_count` 50 → 100.
- `user_data/strategies/TrendEmaAdx.py`: `startup_candle_count` 100 → 200.

All seven strategy files pass `python -m py_compile`. The edited protections were also loaded
through Freqtrade 2026.8's `ProtectionManager` inside the running container without error.
