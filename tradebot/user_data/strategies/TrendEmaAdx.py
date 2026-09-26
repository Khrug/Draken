"""Family 1 - Trend following: EMA crossover gated by ADX trend strength."""
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.strategy import IStrategy

from common_risk import STOPLOSS, PROTECTIONS


class TrendEmaAdx(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    stoploss = STOPLOSS
    minimal_roi = {"0": 0.06}          # trend: let winners run, exit mainly on signal
    startup_candle_count = 200        # EMA55 / ADX14 are recursive: ~4x the longest period
    process_only_new_candles = True

    @property
    def protections(self):
        return PROTECTIONS

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:
        df["ema_fast"] = ta.EMA(df, timeperiod=21)
        df["ema_slow"] = ta.EMA(df, timeperiod=55)
        df["adx"] = ta.ADX(df, timeperiod=14)
        return df

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[
            qtpylib.crossed_above(df["ema_fast"], df["ema_slow"])
            & (df["adx"] > 25)
            & (df["volume"] > 0),
            "enter_long"] = 1
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[
            qtpylib.crossed_below(df["ema_fast"], df["ema_slow"])
            & (df["volume"] > 0),
            "exit_long"] = 1
        return df
