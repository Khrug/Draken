"""Family 3 - Volatility breakout: close above 20-candle high with volume confirmation."""
from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy

from common_risk import STOPLOSS, PROTECTIONS


class BreakoutDonchian(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    stoploss = STOPLOSS
    minimal_roi = {"0": 0.05}
    startup_candle_count = 100        # atr_mean = 50-candle mean of ATR14, shifted: needs >= 65
    process_only_new_candles = True

    @property
    def protections(self):
        return PROTECTIONS

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:
        # shift(1) so the channel uses only past candles (avoids look-ahead bias)
        df["dc_upper"] = df["high"].rolling(20).max().shift(1)
        df["dc_exit"] = df["low"].rolling(10).min().shift(1)
        df["vol_mean"] = df["volume"].rolling(20).mean().shift(1)
        df["atr"] = ta.ATR(df, timeperiod=14)
        df["atr_mean"] = df["atr"].rolling(50).mean().shift(1)
        return df

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[
            (df["close"] > df["dc_upper"])
            & (df["volume"] > 1.5 * df["vol_mean"])
            & (df["atr"] > df["atr_mean"])        # volatility expanding
            & (df["volume"] > 0),
            "enter_long"] = 1
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[(df["close"] < df["dc_exit"]) & (df["volume"] > 0), "exit_long"] = 1
        return df
