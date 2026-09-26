# draken-bot — paper trading

**Status: DRY-RUN ONLY.** No real money is traded. `dry_run: true` in `user_data/config.json`, and no
exchange API keys exist anywhere in this project. Nothing here can place a real order.

Decision rules live in [RULES.md](RULES.md). The plan and research are in [docs/cockpit-plan.html](docs/cockpit-plan.html).

## Venue: Revolut X
Kraken is out (fees, slow trade-based downloads). The target venue is **Revolut X**:

| | Maker | Taker | Source |
|---|---|---|---|
| Revolut X | 0 % | 0.09 % | Revolut X help centre, "Revolut X Fees" (checked 2026-09-26); same values in ccxt's `revolutx` class |

Backtests charge the taker fee (0.09 %) on every buy and every sell, plus a stress run at 0.19 %.

**What works and what does not (be honest about this):**
- **Freqtrade cannot talk to Revolut X.** It is not on Freqtrade's supported-exchange list, and the
  `freqtradeorg/freqtrade:stable` image (2026.8) ships ccxt 4.5.76; the `revolutx` class arrived in
  ccxt 4.5.77. So `freqtrade download-data` and paper/live trading on Revolut X do not work today.
- **Backtests do work**, through a small bridge: `tools/revolutx_candles.py` reads Revolut X's public,
  keyless candle endpoint and writes Freqtrade feather files to `user_data/data/revolutx/`.
  `config.revolutx.json` borrows Bitvavo's market metadata (precision, minimum order size) only so
  Freqtrade can start; all prices come from the Revolut X files.
- **History is short.** Revolut X 1h candles start 2025-11-06; 15m/30m only reach back about one month.
  So the Revolut X matrix is 1h only, and in-sample is 2025-11-06 → 2026-06-26 instead of the
  registered 2025-09-26 start. OOS (2026-06-26 → 2026-09-26) is unchanged, and it is the one judged.
- **The running paper bots still use Bitvavo prices** (see below). Paper trading on Revolut X itself would
  need either a Freqtrade release whose ccxt includes `revolutx` (then a test that Freqtrade accepts it),
  or custom glue code. Real-money trading on Revolut X is not set up and is not planned here.
- **Stop-loss:** the strategies' −3 % stop is enforced by the bot, not by the exchange
  (`stoploss_on_exchange` is almost certainly not available for Revolut X in Freqtrade).
  **The stop only works while the bot is running.** If the PC, Docker or the bot is down, nothing
  protects an open position.

## What runs
`docker compose up -d` starts the paper bots and the cockpit. Every port is bound to 127.0.0.1,
so they are reachable from this PC only.

| Container | What it is | Where |
|---|---|---|
| draken-trend | TrendEmaAdx on 1h candles, Bitvavo prices, €90 paper wallet | FreqUI: http://127.0.0.1:8081 |
| draken-breakout | BreakoutDonchian on 1h candles, Bitvavo prices, €90 paper wallet | FreqUI: http://127.0.0.1:8082 |
| draken-gamma | DrakenGamma (experiment E1) on 1h candles, Bitvavo prices | FreqUI: http://127.0.0.1:8083 |
| draken-cockpit | Teaching dashboard + Telegram reporter | http://127.0.0.1:8090 |

Shared paper settings (`user_data/config.json`): fixed stake €20 per trade, at most 2 open trades,
open orders cancelled when a bot stops (`cancel_open_orders_on_exit: true`).
These take effect the next time a bot is (re)started.

FreqUI login: user `draken`, password = `FREQTRADE__API_SERVER__PASSWORD` in `.env`.

Telegram gets every buy and sell with its result, status changes, warnings, and a summary at
08:00 and 20:00. Pause, resume or stop a bot from the cockpit. There is deliberately no way to
switch to real money from any interface.

## Everyday commands (PowerShell, in `C:\Draken\tradebot`)
```powershell
docker compose ps                 # are the containers up?
docker compose logs -f cockpit    # follow the cockpit log
docker compose restart            # restart everything
docker compose down               # stop everything (paper trades are kept in the .sqlite files)
```

## Research pipeline (Windows, PowerShell, in `C:\Draken\tradebot`)
First time only: copy `.env.example` to `.env` and fill it in (no exchange keys needed).

1. **Download Revolut X candles** (public endpoint, no account/key; about 1 request per second,
   so roughly half a minute for three pairs of 1h):
   ```powershell
   docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/revolutx_candles.py `
     --pairs BTC/EUR ETH/EUR SOL/EUR --timeframes 1h --timerange 20251101-
   ```
   Re-running it later only adds new candles (files are merged). Output: `user_data\data\revolutx\`.

2. **Run the backtest matrix and the gate:**
   ```powershell
   .\run_backtests.ps1
   ```
   3 strategies × 1h × {Revolut X fee 0.09 %, stress 0.19 %} × {IS, OOS}. Then `evaluate.py` applies
   RULES.md. Results: `user_data\results\report.md` (table) and `results.json` (read by the cockpit).
   If PowerShell refuses to run scripts: `powershell -ExecutionPolicy Bypass -File .\run_backtests.ps1`.

The earlier Bitvavo/OKX runs and the experiments E1–E3 (`experiments.py`) still use Bitvavo data and fees.

## Decision rules
The binding rules are in [RULES.md](RULES.md) and are not changed here. In short (v2):
a strategy passes only if, on the **out-of-sample** window, profit after fees > 0, at least 30 trades
and max drawdown ≤ 15 %, **and** its in-sample and full-period returns beat buy-and-hold.
Judge on OOS only; never tune after seeing results — a changed idea is a new registered experiment.
Paper → live needs ≥ 4 weeks and ≥ 20 closed paper trades inside the backtest's predicted range,
and going live is Kai's decision alone.

## Files
- `user_data/config.json` shared settings (dry-run, €90 wallet, €20 stake, 2 open trades).
- `user_data/config.revolutx.json` Revolut X backtest overlay: fee 0.0009, pairs BTC/ETH/SOL-EUR.
- `user_data/config.bitvavo.json` / `config.okx.json` older exchange overlays (paper bots use Bitvavo).
- `tools/revolutx_candles.py` Revolut X public candles → Freqtrade feather files (read-only).
- `user_data/bots/*.json` per-bot name and webhook switch.
- `user_data/strategies/` the strategy families and the shared risk layer.
- `cockpit/` the dashboard (`cockpit.html`) and its small Python service (`server.py`).
- `.env` Telegram token, local API password and secrets. Never commit it.
