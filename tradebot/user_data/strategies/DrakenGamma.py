"""E1 - Coherence across timeframes (registered in RULES.md, 2026-09-26).

Each timeframe (1h, 4h, 1d) is a local view of the market, described by a section vector
s_v = (distance from EMA20, EMA20 slope, RSI momentum), each scaled to [-1, 1].
Gamma = (mean pairwise cosine similarity of the three sections + 1) / 2, in [0, 1].
High Gamma = the views agree (coherent). Trade only when they agree AND point up.
"""
import numpy as np
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, informative

from common_risk import STOPLOSS, PROTECTIONS

VIEWS = ["", "_4h", "_1d"]          # column suffixes: 1h (base), 4h, 1d
COMPONENTS = ["s_dist", "s_slope", "s_mom"]


def add_section(df: DataFrame) -> DataFrame:
    ema = ta.EMA(df, timeperiod=20)
    atr = ta.ATR(df, timeperiod=14)
    rsi = ta.RSI(df, timeperiod=14)
    df["s_dist"] = ((df["close"] - ema) / atr).clip(-3, 3) / 3
    df["s_slope"] = ((ema - ema.shift(3)) / atr).clip(-3, 3) / 3
    df["s_mom"] = (rsi - 50) / 50
    return df


def cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    num = (a * b).sum(axis=1)
    den = np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)
    return np.where(den > 1e-9, num / np.maximum(den, 1e-9), 0.0)


class DrakenGamma(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    stoploss = STOPLOSS
    minimal_roi = {"0": 100}           # no ROI exits: signal or stop only
    startup_candle_count = 1500        # ~62 days: lets the 1d EMA20/ATR14/RSI14 settle
    process_only_new_candles = True

    GAMMA_ENTER = 0.80
    GAMMA_EXIT = 0.55
    CONSENSUS_ENTER = 0.25

    @property
    def protections(self):
        return PROTECTIONS

    # Informative views: Freqtrade merges these onto 1h candles only after the higher
    # timeframe candle has closed, so no future data leaks in.
    @informative("4h")
    def populate_indicators_4h(self, df: DataFrame, metadata: dict) -> DataFrame:
        return add_section(df)

    @informative("1d")
    def populate_indicators_1d(self, df: DataFrame, metadata: dict) -> DataFrame:
        return add_section(df)

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:
        df = add_section(df)
        vecs = [df[[c + v for c in COMPONENTS]].to_numpy(dtype=float) for v in VIEWS]
        sim = (cosine(vecs[0], vecs[1]) + cosine(vecs[0], vecs[2]) + cosine(vecs[1], vecs[2])) / 3
        df["gamma"] = (sim + 1) / 2
        df["consensus"] = np.mean([v.mean(axis=1) for v in vecs], axis=0)
        for i, v in enumerate(vecs):
            df[f"view_mean_{i}"] = v.mean(axis=1)
        # Any missing view (warm-up) makes Gamma undefined rather than falsely coherent
        missing = np.isnan(np.concatenate(vecs, axis=1)).any(axis=1)
        df.loc[missing, ["gamma", "consensus"]] = np.nan
        return df

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[
            (df["gamma"] >= self.GAMMA_ENTER)
            & (df["consensus"] > self.CONSENSUS_ENTER)
            & (df["view_mean_0"] > 0) & (df["view_mean_1"] > 0) & (df["view_mean_2"] > 0)
            & (df["volume"] > 0),
            "enter_long"] = 1
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[
            ((df["gamma"] < self.GAMMA_EXIT) | (df["consensus"] < 0))
            & (df["volume"] > 0),
            "exit_long"] = 1
        return df
