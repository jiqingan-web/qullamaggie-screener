"""
爆涨潜力综合评分。

权重（中文文档，合计 100）：
- 相对强度（1月/3月/6月涨幅百分位）…… 40
  · 1月 45% / 3月 35% / 6月 20%（在 RS 子分内）
- 均线贴近与盘整紧密度………………… 20
- 振幅/波动是否够用（ADR%，利于盈亏比）… 15
- 接近突破 / 近期区间扩张………………… 15
- 前期大涨结构（动量延续）……………… 10
- 纳斯达克软惩罚：QQQ 未站上 10/20 日均线时，总分 ×0.92

硬过滤：近 20 日平均日成交额 ≥ 1000 万美元。
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from universe import get_scan_universe
from screener import (
    analyze_ticker,
    fetch_history,
    fetch_name,
    get_market_filter,
    percentile_rank,
)

from .config import (
    ACCOUNT_USD,
    DEFAULT_RISK_PCT,
    MAX_OVERNIGHT_PCT,
    MIN_DOLLAR_VOLUME,
    TOP_N,
    TYPICAL_SIZE_HIGH,
    TYPICAL_SIZE_LOW,
)

# 对外可引用的权重说明
WEIGHTS = {
    "相对强度": 40,
    "均线贴近与盘整紧密度": 20,
    "振幅波动(ADR%)": 15,
    "接近突破与区间扩张": 15,
    "前期大涨结构": 10,
    "纳指软惩罚倍数": 0.92,
}

POSITION = {
    "账户美元": ACCOUNT_USD,
    "单笔风险默认%": DEFAULT_RISK_PCT * 100,
    "单票仓位%": f"{TYPICAL_SIZE_LOW*100:.0f}–{TYPICAL_SIZE_HIGH*100:.0f}",
    "隔夜单票上限%": MAX_OVERNIGHT_PCT * 100,
    "流动性门槛美元": MIN_DOLLAR_VOLUME,
}


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _range_expansion_score(hist: pd.DataFrame) -> float:
    """近 5 日平均振幅相对近 20 日 ADR 的扩张程度 → 0–100。"""
    try:
        high = hist["High"].astype(float)
        low = hist["Low"].astype(float)
        close = hist["Close"].astype(float)
        if len(close) < 25:
            return 40.0
        adr20 = ((high - low) / close * 100).tail(20).mean()
        adr5 = ((high - low) / close * 100).tail(5).mean()
        if adr20 is None or adr20 <= 0 or (isinstance(adr20, float) and math.isnan(adr20)):
            return 40.0
        ratio = float(adr5) / float(adr20)
        # ratio≈1 → 中性；>1.2 扩张加分；<0.7 收缩（盘整阶段也有价值，给中等分）
        if ratio >= 1.35:
            return 95.0
        if ratio >= 1.15:
            return 80.0
        if ratio >= 0.95:
            return 65.0
        if ratio >= 0.75:
            return 55.0  # 收缩盘整，利于后续爆发
        return 45.0
    except Exception:
        return 40.0


def _tightness_score(row: dict) -> float:
    """均线贴近 + 盘整紧密度 → 0–100。"""
    s = 35.0
    d10 = row.get("距10日均线%")
    d20 = row.get("距20日均线%")
    if d10 is not None:
        # 理想：略高于 10 日均线 0–5%
        if 0 <= d10 <= 5:
            s += 25
        elif -2 <= d10 < 0:
            s += 18
        elif 5 < d10 <= 10:
            s += 12
        elif d10 > 10:
            s += max(0, 10 - (d10 - 10))  # 过高追涨减分
        else:
            s += max(0, 8 + d10)  # 跌破均线
    if d20 is not None:
        if 0 <= d20 <= 8:
            s += 20
        elif -3 <= d20 < 0:
            s += 12
        elif 8 < d20 <= 15:
            s += 8
        else:
            s += 3
    if row.get("盘整"):
        s += 12
    if row.get("贴近均线"):
        s += 10
    if row.get("是否贴近均线盘整"):
        s += 8
    return _clip(s)


def _adr_score(adr: float | None) -> float:
    """波动够用：约 4–10% 最佳（盈亏比空间）；过低难做，过高难拿。"""
    if adr is None:
        return 30.0
    if 5.0 <= adr <= 9.0:
        return 95.0
    if 4.0 <= adr < 5.0 or 9.0 < adr <= 12.0:
        return 80.0
    if 3.0 <= adr < 4.0 or 12.0 < adr <= 15.0:
        return 60.0
    if adr < 3.0:
        return 25.0
    return 40.0  # 极高波动


def _breakout_score(row: dict, expansion: float) -> float:
    s = 20.0
    if row.get("接近突破"):
        s += 45
    if row.get("是否贴近均线盘整") and row.get("接近突破"):
        s += 20
    s += expansion * 0.25  # 扩张子分贡献一部分
    return _clip(s)


def _structure_score(row: dict) -> float:
    s = 25.0
    if row.get("前期大涨"):
        s += 50
    if row.get("盘整") and row.get("前期大涨"):
        s += 25
    return _clip(s)


def _position_shares(last: float, stop: float) -> dict[str, Any]:
    risk_usd = ACCOUNT_USD * DEFAULT_RISK_PCT
    risk_per = last - stop
    by_risk = int(risk_usd / risk_per) if risk_per > 0 else 0
    max_overnight = int((ACCOUNT_USD * MAX_OVERNIGHT_PCT) / last) if last > 0 else 0
    lo = int((ACCOUNT_USD * TYPICAL_SIZE_LOW) / last) if last > 0 else 0
    hi = int((ACCOUNT_USD * TYPICAL_SIZE_HIGH) / last) if last > 0 else 0
    suggested = min(by_risk, max_overnight, hi) if hi > 0 else 0
    notional = suggested * last
    return {
        "建议仓位股数": suggested,
        "按风险股数": by_risk,
        "隔夜上限股数": max_overnight,
        "典型仓位股数区间": f"{lo}–{hi}",
        "建议市值美元": round(notional, 2),
        "建议仓位占比%": round(notional / ACCOUNT_USD * 100, 2) if ACCOUNT_USD else 0,
        "风险美元": round(risk_usd, 2),
    }


def score_burst(row: dict, rs_pct: float, expansion: float, market_green: bool) -> dict[str, float]:
    """返回各子分与总分（0–100）。"""
    rs = _clip(rs_pct)
    ma = _tightness_score(row)
    adr = _adr_score(row.get("20日平均振幅%"))
    bo = _breakout_score(row, expansion)
    st = _structure_score(row)

    total = (
        rs * 0.40
        + ma * 0.20
        + adr * 0.15
        + bo * 0.15
        + st * 0.10
    )
    if not market_green:
        total *= WEIGHTS["纳指软惩罚倍数"]

    return {
        "相对强度子分": round(rs, 1),
        "均线盘整子分": round(ma, 1),
        "振幅子分": round(adr, 1),
        "突破扩张子分": round(bo, 1),
        "结构子分": round(st, 1),
        "爆涨分": round(_clip(total), 1),
    }


def run_top5(
    max_workers: int = 12,
    progress_cb=None,
) -> dict[str, Any]:
    """全池扫描并输出 TOP5 爆涨潜力名单。"""
    tickers = get_scan_universe()
    market = get_market_filter()
    market_green = bool(market.get("绿色区域"))

    rows: list[dict] = []
    hists: dict[str, pd.DataFrame] = {}
    errors = 0
    total = len(tickers)

    try:
        data = yf.download(
            tickers,
            period="1y",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=True,
        )
    except Exception:
        data = None

    def hist_for(t: str) -> pd.DataFrame | None:
        if data is None:
            return fetch_history(t)
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if t not in data.columns.get_level_values(0):
                    return None
                sub = data[t].dropna(how="all")
            else:
                sub = data.dropna(how="all")
            if sub is None or sub.empty or len(sub) < 50:
                return None
            return sub.rename(columns=str.title)
        except Exception:
            return fetch_history(t)

    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(analyze_ticker, t, hist_for(t)): t for t in tickers}
        for fut in as_completed(futs):
            t = futs[fut]
            done += 1
            if progress_cb and done % 20 == 0:
                progress_cb(done, total)
            try:
                r = fut.result()
                if r:
                    h = hist_for(t)
                    if h is not None:
                        hists[t] = h
                    rows.append(r)
                else:
                    errors += 1
            except Exception:
                errors += 1

    empty = {
        "更新时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "时区": "Asia/Shanghai",
        "账户美元": ACCOUNT_USD,
        "流动性门槛美元": MIN_DOLLAR_VOLUME,
        "仓位规则": POSITION,
        "权重说明": WEIGHTS,
        "市场过滤": market,
        "结果": [],
        "统计": {"扫描数": total, "有效": 0, "失败": errors, "入选": 0},
    }
    if not rows:
        return empty

    df = pd.DataFrame(rows)
    df = df[df["日成交额"] >= MIN_DOLLAR_VOLUME].copy()
    if df.empty:
        empty["统计"] = {"扫描数": total, "有效": len(rows), "失败": errors, "流动性后": 0, "入选": 0}
        return empty

    for col in ("1月涨幅", "3月涨幅", "6月涨幅"):
        df[f"{col}_百分位"] = percentile_rank(df[col].fillna(-999))

    df["RS分"] = (
        df["1月涨幅_百分位"] * 0.45
        + df["3月涨幅_百分位"] * 0.35
        + df["6月涨幅_百分位"] * 0.20
    )

    scored: list[dict] = []
    for _, row in df.iterrows():
        d = row.to_dict()
        ticker = d["代码"]
        expansion = _range_expansion_score(hists[ticker]) if ticker in hists else 40.0
        parts = score_burst(d, float(d["RS分"]), expansion, market_green)

        last = float(d["最新价"])
        stop = float(d["建议止损"])
        pos = _position_shares(last, stop)

        # 用收紧仓位覆盖 screener 默认建议
        out = {
            "代码": ticker,
            "名称": d.get("名称") or ticker,
            "最新价": d["最新价"],
            "1月涨幅": d.get("1月涨幅"),
            "3月涨幅": d.get("3月涨幅"),
            "6月涨幅": d.get("6月涨幅"),
            "日成交额": int(d["日成交额"]) if d.get("日成交额") is not None else None,
            "20日平均振幅%": d.get("20日平均振幅%"),
            "距10日均线%": d.get("距10日均线%"),
            "距20日均线%": d.get("距20日均线%"),
            "是否贴近均线盘整": bool(d.get("是否贴近均线盘整")),
            "前期大涨": bool(d.get("前期大涨")),
            "盘整": bool(d.get("盘整")),
            "贴近均线": bool(d.get("贴近均线")),
            "接近突破": bool(d.get("接近突破")),
            "区间扩张子分原始": round(expansion, 1),
            "建议止损": d.get("建议止损"),
            "RS分": round(float(d["RS分"]), 1),
            **parts,
            **pos,
        }
        scored.append(out)

    scored.sort(key=lambda x: x["爆涨分"], reverse=True)
    top = scored[:TOP_N]

    # 补名称
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(fetch_name, r["代码"]): r for r in top}
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                r["名称"] = fut.result()
            except Exception:
                pass

    # 排名
    for i, r in enumerate(top, 1):
        r["排名"] = i

    return {
        "更新时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "时区": "Asia/Shanghai",
        "账户美元": ACCOUNT_USD,
        "流动性门槛美元": MIN_DOLLAR_VOLUME,
        "仓位规则": POSITION,
        "权重说明": {
            "相对强度": "40（1月45% / 3月35% / 6月20%）",
            "均线贴近与盘整紧密度": 20,
            "振幅波动(ADR%)": 15,
            "接近突破与区间扩张": 15,
            "前期大涨结构": 10,
            "纳指软惩罚": "QQQ 未站上 10/20 日均线时总分 ×0.92",
        },
        "市场过滤": market,
        "结果": top,
        "统计": {
            "扫描数": total,
            "有效分析": len(rows),
            "失败": errors,
            "流动性后": int(len(df)),
            "入选": len(top),
            "模型": "爆涨潜力综合分 TOP5",
        },
    }
