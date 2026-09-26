"""Shared risk layer: identical for every strategy family so comparisons are fair.

Durations are in minutes so each rule means the same wall-clock time on any timeframe.
"""

STOPLOSS = -0.03  # hard stop, 3 % per trade

PROTECTIONS = [
    # Pause a pair for 25 minutes after any exit (shorter than one 30m/1h candle, so it only
    # has an effect on 15m)
    {"method": "CooldownPeriod", "stop_duration": 25},
    # Stop all trading for 12 h if 3 stop-losses hit within 24 h
    {"method": "StoplossGuard", "lookback_period": 1440, "trade_limit": 3,
     "stop_duration": 720, "only_per_pair": False},
    # Soft daily loss cap: block NEW entries for 24 h once realised (closed-trade) equity
    # drawdown over the last 24 h exceeds 5 % of the account. It does not close open trades
    # and ignores unrealised losses. "equity" mode measures % of account; the default
    # "ratios" mode sums per-trade % instead. trade_limit 1 so it can fire at our trade rate
    # (with 5 it needed 5 closed trades inside 24 h, which ~0.5 trades/day almost never gives).
    {"method": "MaxDrawdown", "calculation_mode": "equity", "lookback_period": 1440,
     "trade_limit": 1, "stop_duration": 1440, "max_allowed_drawdown": 0.05},
]
