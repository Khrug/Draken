# Backtest matrix on Revolut X candles: 3 strategy families x 1h x 2 fee levels, IS vs OOS.
# Dry-run research only: backtesting never places orders and needs no API key.
#
# Data: Revolut X public candles, fetched by tools/revolutx_candles.py into user_data/data/revolutx
#       (Freqtrade cannot download from Revolut X itself). Run that first - see README.
# Fee:  Revolut X taker 0.09 % per side, maker 0 % (Revolut X help centre "Revolut X Fees",
#       checked 2026-09-26; ccxt's revolutx class uses the same 0.0009 / 0). We charge the
#       taker fee on every fill, which is the conservative case.
# Stress variant: fee + 0.10 % per side (0.19 %) to cover spread/slippage on a thinner book.
#
# Windows: OOS = 2026-06-26 -> 2026-09-26 (as registered). IS would start 2025-09-26, but Revolut X
# 1h history only begins 2025-11-06, so IS here = 2025-11-06 -> 2026-06-26 (data-limited, see README).
# 15m/30m are not tested: Revolut X keeps only about one month of them.
# Judge ONLY on out-of-sample (python evaluate.py applies RULES.md).
#
# Market metadata (precision, min order) comes from the "bitvavo" ccxt class in config.revolutx.json,
# because the Freqtrade image cannot load Revolut X markets. Prices come from the Revolut X files.

$ErrorActionPreference = "Continue"
$strategies = @("TrendEmaAdx", "MeanRevBbRsi", "BreakoutDonchian")
$timeframes = @("1h")
$ranges = [ordered]@{ "IS" = "20251106-20260626"; "OOS" = "20260626-20260926" }
$venues = [ordered]@{
  "revolutx"        = "0.0009"   # Revolut X taker fee
  "revolutx-stress" = "0.0019"   # taker fee + 0.10 % per side
}
$datadir = "user_data/data/revolutx"

foreach ($tf in $timeframes) {
  foreach ($p in @("BTC_EUR", "ETH_EUR", "SOL_EUR")) {
    if (-not (Test-Path "user_data\data\revolutx\$p-$tf.feather")) {
      Write-Error "Missing $datadir/$p-$tf.feather - run tools/revolutx_candles.py first (see README)."
      exit 1
    }
  }
}

New-Item -ItemType Directory -Force -Path "user_data\results" | Out-Null
foreach ($venue in $venues.Keys) {
  $fee = $venues[$venue]
  foreach ($r in $ranges.Keys) {
    foreach ($s in $strategies) {
      foreach ($tf in $timeframes) {
        $name = "${venue}_${r}_${s}_${tf}"
        Write-Host "=== $name (fee $fee) ==="
        New-Item -ItemType Directory -Force -Path "user_data\backtest_results\$name" | Out-Null
        docker compose run --rm freqtrade backtesting `
          --config user_data/config.json --config user_data/config.revolutx.json `
          --datadir $datadir --fee $fee `
          --strategy $s --timeframe $tf `
          --timerange $($ranges[$r]) `
          --export trades --cache none --enable-protections `
          --backtest-directory "user_data/backtest_results/$name" `
          | Tee-Object -FilePath "user_data\results\$name.txt"
        if ($LASTEXITCODE -ne 0) { Write-Warning "$name failed (exit $LASTEXITCODE)" }
      }
    }
  }
}

python evaluate.py --telegram
