"""Download Revolut X candles into Freqtrade's data format, so backtests can run on Revolut X prices.

Why this exists: Freqtrade cannot talk to Revolut X. ccxt added a `revolutx` class in 4.5.77,
but the freqtrade:stable image (2026.8) ships ccxt 4.5.76, and Revolut X is not on Freqtrade's
supported-exchange list. So `freqtrade download-data --exchange revolutx` does not work.

READ-ONLY. Uses only the public, unauthenticated market-data endpoint
    GET https://revx.revolut.com/api/1.0/public/candles/{BASE-QUOTE}?interval=<min>&since=<ms>&until=<ms>
No API key, no account access, no orders.

Measured limits of the public endpoint (2026-09-26):
  * max 1000 candles per request, ~1 request/second (HTTP 429 "Rate limit exceeded" otherwise)
  * history depth: 1h and 1d go back to 2025-11-06; 15m and 30m only to ~2026-08-28
  * hours without trades may be missing -> Freqtrade fills them as flat candles on load

Run it inside the Freqtrade image (it has pandas/pyarrow and Freqtrade's own data writer):
    docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/revolutx_candles.py `
      --pairs BTC/EUR ETH/EUR SOL/EUR --timeframes 1h --timerange 20251101-

Output: user_data/data/revolutx/<BASE>_<QUOTE>-<tf>.feather (merged with what is already there).
Backtest with:  --datadir user_data/data/revolutx  (see run_backtests.ps1).
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://revx.revolut.com/api/1.0/public/candles/{symbol}"
TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
CHUNK = 900          # candles per request (endpoint max is 1000; keep margin, `until` is inclusive)
PAUSE = 1.2          # seconds between requests (public limit is ~1/s)


def parse_timerange(tr: str) -> tuple[int, int]:
    """Freqtrade-style YYYYMMDD-[YYYYMMDD] -> (since_ms, until_ms) in UTC."""
    start, _, end = tr.partition("-")
    to_ms = lambda s: int(datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc).timestamp() * 1000)  # noqa: E731
    now = int(time.time() * 1000)
    return to_ms(start), (to_ms(end) if end else now)


def get_json(url: str, retries: int = 6) -> dict:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "draken-bot-candles/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(PAUSE * (attempt + 2))
                continue
            raise SystemExit(f"HTTP {e.code} for {url}: {e.read()[:300]!r}")
        except urllib.error.URLError:
            time.sleep(PAUSE * (attempt + 2))
    raise SystemExit(f"giving up after {retries} attempts: {url}")


def fetch(pair: str, tf: str, since: int, until: int, region: str | None) -> list[list]:
    step = TF_MINUTES[tf] * 60_000
    symbol = pair.replace("/", "-")
    now = int(time.time() * 1000)
    rows: dict[int, list] = {}
    t = since - since % step
    while t < until:
        end = min(t + (CHUNK - 1) * step, until)
        url = API.format(symbol=symbol) + f"?interval={TF_MINUTES[tf]}&since={t}&until={end}"
        if region:
            url += f"&region={region}"
        for c in get_json(url).get("data", []):
            start = int(c["start"])
            if since <= start < until and start + step <= now:     # skip the still-open candle
                rows[start] = [start, float(c["open"]), float(c["high"]), float(c["low"]),
                               float(c["close"]), float(c["volume"])]
        t = end + step
        time.sleep(PAUSE)
    return [rows[k] for k in sorted(rows)]


def store(datadir: Path, pair: str, tf: str, rows: list[list], fmt: str) -> tuple[int, str, str]:
    import pandas as pd
    from freqtrade.data.history import get_datahandler
    from freqtrade.enums import CandleType

    new = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    new["date"] = pd.to_datetime(new["date"], unit="ms", utc=True)
    dh = get_datahandler(datadir, fmt)
    old = dh.ohlcv_load(pair, tf, candle_type=CandleType.SPOT, fill_missing=False, drop_incomplete=False)
    df = pd.concat([old, new]) if not old.empty else new
    df = df.drop_duplicates(subset="date", keep="last").sort_values("date").reset_index(drop=True)
    dh.ohlcv_store(pair, tf, df, candle_type=CandleType.SPOT)
    return len(df), str(df["date"].iloc[0]), str(df["date"].iloc[-1])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", nargs="+", default=["BTC/EUR", "ETH/EUR", "SOL/EUR"])
    ap.add_argument("--timeframes", nargs="+", default=["1h"], choices=sorted(TF_MINUTES))
    ap.add_argument("--timerange", default="20251101-", help="YYYYMMDD-[YYYYMMDD], UTC")
    ap.add_argument("--datadir", default="/freqtrade/user_data/data/revolutx")
    ap.add_argument("--data-format", default="feather", choices=["feather", "json", "parquet"])
    ap.add_argument("--region", default=None, help="optional, e.g. EEA (default: the API's choice)")
    args = ap.parse_args()

    since, until = parse_timerange(args.timerange)
    datadir = Path(args.datadir)
    datadir.mkdir(parents=True, exist_ok=True)
    for tf in args.timeframes:
        step = TF_MINUTES[tf] * 60_000
        for pair in args.pairs:
            rows = fetch(pair, tf, since, until, args.region)
            if not rows:
                print(f"{pair} {tf}: no candles returned for this range", flush=True)
                continue
            expected = (rows[-1][0] - rows[0][0]) // step + 1
            n, first, last = store(datadir, pair, tf, rows, args.data_format)
            print(f"{pair} {tf}: +{len(rows)} candles ({expected - len(rows)} missing bars in range), "
                  f"file now {n} candles {first} -> {last}", flush=True)
    print(f"Done. Data in {datadir}", file=sys.stderr)


if __name__ == "__main__":
    main()
