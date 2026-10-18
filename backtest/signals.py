"""相对强度、盘整突破、市场过滤信号。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (
    BREAKOUT_LOOKBACK,
    CONSOL_LOOKBACK,
    CONSOL_RANGE_PCT_MAX,
    MA_NEAR_PCT,
    MIN_DOLLAR_VOLUME,
    PRIOR_MOVE_LOOKBACK,
    PRIOR_MOVE_MIN_PCT,
    RS_TOP_PCT,
    TRAIL_MA,
)


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """为单标的日线添加指标列。"""
    out = df.copy()
    c = out["Close"]
    h = out["High"]
    l = out["Low"]
    v = out["Volume"]
    out["ma10"] = c.rolling(10).mean()
    out["ma20"] = c.rolling(20).mean()
    out["dollar_vol20"] = (c * v).rolling(20).mean()
    out["adr20"] = ((h - l) / c * 100).rolling(20).mean()
    out["ret_1m"] = c.pct_change(21)
    out["ret_3m"] = c.pct_change(63)
    out["ret_6m"] = c.pct_change(126)
    out["hh_n"] = h.rolling(BREAKOUT_LOOKBACK).max().shift(1)  # 不含当日，突破用
    # 盘整区间：近 CONSOL_LOOKBACK 日（不含当日）高低振幅
    roll_high = h.rolling(CONSOL_LOOKBACK).max().shift(1)
    roll_low = l.rolling(CONSOL_LOOKBACK).min().shift(1)
    out["consol_range_pct"] = (roll_high - roll_low) / c * 100
    # 前期大涨：更早窗口内高/低
    prior = c.shift(BREAKOUT_LOOKBACK)
    prior_low = prior.rolling(PRIOR_MOVE_LOOKBACK - BREAKOUT_LOOKBACK).min()
    prior_high = prior.rolling(PRIOR_MOVE_LOOKBACK - BREAKOUT_LOOKBACK).max()
    out["prior_move_pct"] = (prior_high / prior_low - 1.0) * 100
    out["dist_ma10"] = (c / out["ma10"] - 1.0) * 100
    out["dist_ma20"] = (c / out["ma20"] - 1.0) * 100
    return out


def market_green(market: pd.DataFrame) -> pd.Series:
    """QQQ 收盘同时站上 10/20 日均线且均线向上 → True。"""
    m = market.copy()
    c = m["Close"]
    ma10 = c.rolling(10).mean()
    ma20 = c.rolling(20).mean()
    return (c > ma10) & (c > ma20) & (ma10 >= ma20)


def build_panels(prices: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {t: enrich(df) for t, df in prices.items() if df is not None and len(df) >= 130}


def rs_candidates_on_date(
    panels: dict[str, pd.DataFrame],
    date: pd.Timestamp,
    top_pct: float = RS_TOP_PCT,
) -> set[str]:
    """当日流动性过滤后，按 1m/3m/6m 综合分取前约 top_pct%。"""
    rows = []
    for t, df in panels.items():
        if date not in df.index:
            continue
        row = df.loc[date]
        dv = row.get("dollar_vol20")
        if pd.isna(dv) or float(dv) < MIN_DOLLAR_VOLUME:
            continue
        r1, r3, r6 = row.get("ret_1m"), row.get("ret_3m"), row.get("ret_6m")
        if pd.isna(r1) and pd.isna(r3) and pd.isna(r6):
            continue
        rows.append((t, r1, r3, r6))
    if len(rows) < 10:
        return set()
    rdf = pd.DataFrame(rows, columns=["t", "r1", "r3", "r6"])
    for col in ("r1", "r3", "r6"):
        rdf[f"{col}_p"] = rdf[col].rank(pct=True, method="average") * 100
    rdf["rs"] = rdf["r1_p"].fillna(0) * 0.45 + rdf["r3_p"].fillna(0) * 0.35 + rdf["r6_p"].fillna(0) * 0.20
    thr = 100 - top_pct
    pick = rdf[
        (rdf["r1_p"] >= thr) | (rdf["r3_p"] >= thr) | (rdf["r6_p"] >= thr) | (rdf["rs"] >= rdf["rs"].quantile(0.92))
    ]
    # 再收紧到约 top_pct * 1.5 只，避免过宽
    n = max(3, int(np.ceil(len(rdf) * top_pct / 100.0 * 1.5)))
    pick = pick.sort_values("rs", ascending=False).head(n)
    return set(pick["t"].tolist())


def is_breakout_entry(row: pd.Series) -> bool:
    """日线近似：收盘突破近期高点 + 盘整/贴近均线 + 前期有大涨。"""
    if pd.isna(row.get("Close")) or pd.isna(row.get("hh_n")):
        return False
    close = float(row["Close"])
    hh = float(row["hh_n"])
    if close <= hh:
        return False
    # 流动性
    dv = row.get("dollar_vol20")
    if pd.isna(dv) or float(dv) < MIN_DOLLAR_VOLUME:
        return False
    consol = row.get("consol_range_pct")
    if pd.isna(consol) or float(consol) > CONSOL_RANGE_PCT_MAX:
        return False
    ma10, ma20 = row.get("ma10"), row.get("ma20")
    if pd.isna(ma10) or pd.isna(ma20):
        return False
    if not (float(ma10) > float(ma20) * 0.995 and close >= float(ma20) * 0.97):
        return False
    dist10 = row.get("dist_ma10")
    if pd.isna(dist10) or abs(float(dist10)) > MA_NEAR_PCT + 6:  # 突破当日可略远
        # 突破日允许稍远离均线
        if pd.isna(dist10) or float(dist10) > 18:
            return False
    prior = row.get("prior_move_pct")
    if pd.isna(prior) or float(prior) < PRIOR_MOVE_MIN_PCT:
        return False
    return True


def stop_price(entry: float, day_low: float, adr_pct: float | None) -> float:
    """止损：入场日低，若过宽则用 ADR 封顶（取更高止损价 = 更紧风险）。"""
    stop = float(day_low)
    if adr_pct is not None and not pd.isna(adr_pct) and float(adr_pct) > 0:
        adr_stop = entry - (float(adr_pct) / 100.0) * entry
        stop = max(stop, adr_stop)
    if stop >= entry:
        stop = entry * 0.95
    return float(stop)


def trail_exit_signal(row: pd.Series) -> bool:
    """收盘跌破 10 日均线 → 余仓离场。"""
    c, ma = row.get("Close"), row.get("ma10")
    if pd.isna(c) or pd.isna(ma):
        return False
    return float(c) < float(ma)
