# Decision rules

Rules are written down before the results they judge. Changing a rule after seeing
results is only allowed as a new version, and the new version binds only future tests.

## v1 — 2026-09-25 (before any backtest)
A strategy passes if, on the out-of-sample (OOS) window:
1. profit after fees > 0
2. at least 30 trades
3. max drawdown <= 15 %

## v2 — 2026-09-26 (written after seeing the v1 results)
The v1 matrix showed that the OOS window (Jun–Sep 2026, market +64 %) rewarded any
long-only strategy just for being in the market, while every strategy lost in the
in-sample window (Sep 2025–Jun 2026, market −56 %). v1 could not tell edge from market
direction. v2 keeps all v1 rules and adds:

4. In-sample return must beat buy-and-hold over the in-sample window.
5. Full-period return (IS and OOS compounded) must beat buy-and-hold over the full period.

Honesty note: v2 was written after the v1 results were known, so its verdicts on the
first matrix are informational only. It becomes binding for every strategy tested from
now on. The 30-trade minimum is deliberately left unchanged, even though it is what fails
TrendEmaAdx 1h — lowering it now would be fitting the rules to a result.

## Paper trading → live (applies later)
- At least 4 weeks of paper trading, and at least 20 closed trades.
- Paper result must stay inside the range the backtest predicted.
- Going live is Kai's decision alone, with a trade-only API key (no withdrawals)
  and a hard loss limit set before the first trade.

## Experiments registered 2026-09-26 (parameters fixed before any run)
All three: Bitvavo, taker fee 0.25 %, same windows as the matrix (IS 2025-09-26 → 2026-06-26,
OOS 2026-06-26 → 2026-09-26), judged by v2. No parameter is changed after seeing results;
a changed idea is registered here as a new experiment with a new name.

### E1 DrakenGamma — coherence across timeframes
- Pairs BTC/ETH/SOL, base 1h, three views: 1h, 4h, 1d (informative, merged without lookahead).
- Section per view s_v = (clip((close−EMA20)/ATR14, ±3)/3, clip((EMA20−EMA20[−3])/ATR14, ±3)/3, (RSI14−50)/50).
- Γ = (mean pairwise cosine similarity of the three sections + 1) / 2, in [0, 1]. High = coherent.
- Consensus c = mean of all section components.
- Enter when Γ ≥ 0.80, c > 0.25 and every view's mean component > 0. Exit when Γ < 0.55 or c < 0.
- Shared risk layer (stop −3 %, protections). No ROI table (exit by signal or stop).

### E2 MomentumRotation — hold the strongest coins
- Universe (fixed): top 30 Bitvavo EUR pairs by 24h volume on 2026-09-26 with complete 1h data
  from 2025-05-01. Known bias: selecting by today's volume favours coins that survived and grew.
- Momentum = 168-hour (7-day) return. Rank across the universe every hour.
- Regime filter: BTC/EUR close > its 480-hour (20-day) simple moving average.
- Enter when rank ≤ 3, momentum > 0 and regime on. Exit when rank > 6, momentum < 0 or regime off.
- Max 3 open trades (~€30 each). Stop −10 % (alts move 3 % in an hour; exits are rank-based),
  shared protections otherwise.

### E3 FreqAIRegime — machine-learning forecast
- Pairs BTC/ETH/SOL, base 1h, LightGBMRegressor, features on 1h and 4h plus BTC/EUR as correlated
  pair, indicator periods 10/20/50, 2 shifted candles, dissimilarity-index outlier filter 0.9.
- Target: mean close over the next 24 candles relative to now, minus 1.
- Train on the previous 90 days, retrain every 7 days (walk-forward: never trains on the future).
- Enter when prediction > +1.0 % and the model is not flagging the input as an outlier.
  Exit when prediction < 0. Shared risk layer.

### Audit corrections 2026-09-26 (implementation only, no strategy parameter changed)
An independent review found that backtests ran WITHOUT the shared protections (Freqtrade needs
`--enable-protections` in backtesting), so they did not test what the paper bots run. Fixed in
both runners; the whole matrix and E1–E3 are re-run. Also brought into line with the spec:
E3 now fits on the full 90 days (it held back the newest 25 % as an eval set), fresh model
identifier regime-v1b; warm-up raised for E1 (1d view) and E3 (4h features).
Noted, not changed: E1 and E3 use max 2 open trades (base config, same as the matrix);
E2's universe has data gaps in PHA, GRASS, UNI, BCH, PENGU and ENA (filled as flat candles).
Out-of-sample smoke runs of E1 and E2 had been seen before this correction.

## v3 — 2026-09-26 (paper bots only; no strategy rule changed)
Written after the safety audit and the first Revolut X matrix. Binds future tests only.
- Venue is Revolut X (taker 0.09 %, maker 0 %). Freqtrade cannot connect to it, so backtests use
  Revolut X candles via tools/revolutx_candles.py; the paper bots still read Bitvavo prices but
  now charge the Revolut X fee (0.09 %, set in user_data/bots/*.json).
- Paper bots trade a fixed 20 EUR per trade, max 2 open (base config.json), instead of
  "unlimited" (~44.55 EUR). Reason: three bots would overlap on one real 90 EUR account.
- E1–E3 keep the stake they were registered and run with ("unlimited" of the wallet),
  pinned via user_data/config.registered.json, so their results stay comparable. Any new
  experiment at 20 EUR is registered under a new name.
- The Revolut X matrix's in-sample window starts 2025-11-06 (earliest Revolut X 1h data),
  not 2025-09-26. The OOS window is unchanged.
