"""E3 - Machine-learning forecast with FreqAI (registered in RULES.md, 2026-09-26).

A LightGBM model predicts the average price over the next 24 hours relative to now.
It is retrained every 7 days on the previous 90 days only (walk-forward), so it never
sees the future it is judged on. Buy when it expects more than +1 %, sell when it
expects a fall. Needs the freqtradeorg/freqtrade:stable_freqai image and config.freqai.json.
"""
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from pandas import DataFrame
from freqtrade.strategy import IStrategy

from common_risk import STOPLOSS, PROTECTIONS

ENTER_ABOVE = 0.01


class FreqAIRegime(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    stoploss = STOPLOSS
    minimal_roi = {"0": 100}
    startup_candle_count = 240        # 50-period indicators on 4h candles
    process_only_new_candles = True

    @property
    def protections(self):
        return PROTECTIONS

    # Features: FreqAI expands these over the configured timeframes (1h, 4h),
    # periods (10, 20, 50), shifted candles and the correlated pair (BTC/EUR).
    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int,
                                       metadata: dict, **kwargs) -> DataFrame:
        dataframe["%-rsi-period"] = ta.RSI(dataframe, timeperiod=period)
        dataframe["%-mfi-period"] = ta.MFI(dataframe, timeperiod=period)
        dataframe["%-adx-period"] = ta.ADX(dataframe, timeperiod=period)
        dataframe["%-roc-period"] = ta.ROC(dataframe, timeperiod=period)
        dataframe["%-relative_volume-period"] = (
            dataframe["volume"] / dataframe["volume"].rolling(period).mean())
        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=period, stds=2.2)
        dataframe["%-bb_width-period"] = (bb["upper"] - bb["lower"]) / bb["mid"]
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict,
                                         **kwargs) -> DataFrame:
        dataframe["%-pct-change"] = dataframe["close"].pct_change()
        dataframe["%-raw_volume"] = dataframe["volume"]
        return dataframe

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict,
                                     **kwargs) -> DataFrame:
        dataframe["%-day_of_week"] = dataframe["date"].dt.dayofweek
        dataframe["%-hour_of_day"] = dataframe["date"].dt.hour
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        # Mean close over the NEXT label_period candles, relative to now. Only used for
        # training; FreqAI drops rows whose future is unknown.
        n = self.freqai_info["feature_parameters"]["label_period_candles"]
        dataframe["&-s_close"] = (
            dataframe["close"].shift(-n).rolling(n).mean() / dataframe["close"] - 1)
        return dataframe

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:
        return self.freqai.start(df, metadata, self)

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[
            (df["do_predict"] == 1) & (df["&-s_close"] > ENTER_ABOVE) & (df["volume"] > 0),
            "enter_long"] = 1
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[(df["&-s_close"] < 0) & (df["volume"] > 0), "exit_long"] = 1
        return df
