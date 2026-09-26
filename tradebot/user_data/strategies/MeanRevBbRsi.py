"""Family 2 - Mean reversion: close below lower Bollinger band with oversold RSI."""
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.strategy import IStrategy

from common_risk import STOPLOSS, PROTECTIONS


class MeanRevBbRsi(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    stoploss = STOPLOSS
    minimal_roi = {"0": 0.02, "30": 0.01}   # reversion: take quick profits
    startup_candle_count = 50
    process_only_new_candles = True

    @property
    def protections(self):
        return PROTECTIONS

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:
        bb = qtpylib.bollinger_bands(qtpylib.typical_price(df), window=20, stds=2)
        df["bb_lower"], df["bb_mid"], df["bb_upper"] = bb["lower"], bb["mid"], bb["upper"]
        df["rsi"] = ta.RSI(df, timeperiod=14)
        return df

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[
            (df["close"] < df["bb_lower"])
            & (df["rsi"] < 30)
            & (df["volume"] > 0),
            "enter_long"] = 1
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[
            ((df["close"] > df["bb_mid"]) | (df["rsi"] > 60))
            & (df["volume"] > 0),
            "exit_long"] = 1
        return df
