"""E2 - Momentum rotation (registered in RULES.md, 2026-09-26).

Rank a fixed universe of 30 Bitvavo EUR coins by 7-day return every hour and hold the
3 strongest, but only while BTC is above its 20-day average. Rank <= 3 to enter,
rank > 6 to exit (a buffer so the bot doesn't churn fees on small rank changes).
"""
from pandas import DataFrame
from freqtrade.strategy import IStrategy

from common_risk import PROTECTIONS

# Top 30 by 24h volume on 2026-09-26 with complete 1h history from 2025-05-01.
# Known bias: chosen with today's knowledge (see RULES.md E2).
UNIVERSE = [
    "XRP/EUR", "BTC/EUR", "SOL/EUR", "ETH/EUR", "ADA/EUR", "NEAR/EUR", "SUI/EUR", "HYPE/EUR",
    "ONDO/EUR", "LINK/EUR", "FET/EUR", "TAO/EUR", "QNT/EUR", "PHA/EUR", "LTC/EUR", "WLD/EUR",
    "XLM/EUR", "AVAX/EUR", "ENA/EUR", "PEPE/EUR", "DOGE/EUR", "UNI/EUR", "HBAR/EUR", "RENDER/EUR",
    "SEI/EUR", "BCH/EUR", "GRASS/EUR", "PENGU/EUR", "AAVE/EUR", "ARB/EUR",
]
MOM_CANDLES = 168      # 7 days of 1h candles
REGIME_CANDLES = 480   # 20 days
TOP_ENTER = 3
TOP_EXIT = 6


class MomentumRotation(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    stoploss = -0.10
    minimal_roi = {"0": 100}           # exits are rank-based
    startup_candle_count = REGIME_CANDLES + 10
    process_only_new_candles = True

    @property
    def protections(self):
        return PROTECTIONS

    def informative_pairs(self):
        return [(p, self.timeframe) for p in UNIVERSE]

    def _closes(self, pair: str, df: DataFrame, own_pair: str):
        other = df if pair == own_pair else self.dp.get_pair_dataframe(pair, self.timeframe)
        if other is None or other.empty:
            return None
        return other.set_index("date")["close"]

    def populate_indicators(self, df: DataFrame, metadata: dict) -> DataFrame:
        own = metadata["pair"]
        moms = {}
        for p in UNIVERSE:
            close = self._closes(p, df, own)
            if close is not None:
                moms[p] = close / close.shift(MOM_CANDLES) - 1
        # Align every coin on the same timestamps: each row only uses closes at that time
        m = DataFrame(moms)
        ranks = m.rank(axis=1, ascending=False)
        btc = self._closes("BTC/EUR", df, own)
        regime = btc > btc.rolling(REGIME_CANDLES).mean()

        dates = df["date"]
        df["mom"] = m[own].reindex(dates).to_numpy()
        df["rank"] = ranks[own].reindex(dates).to_numpy()
        df["regime"] = regime.reindex(dates).fillna(False).astype(bool).to_numpy()
        return df

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[
            (df["rank"] <= TOP_ENTER) & (df["mom"] > 0) & df["regime"] & (df["volume"] > 0),
            "enter_long"] = 1
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df.loc[
            ((df["rank"] > TOP_EXIT) | (df["mom"] < 0) | ~df["regime"]) & (df["volume"] > 0),
            "exit_long"] = 1
        return df
