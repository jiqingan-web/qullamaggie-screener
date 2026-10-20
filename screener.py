"""
Qullamaggie（Kristjan Kullamägi）风格美股筛选核心逻辑。
账户固定 100,000 美元；流动性门槛 = 账户 × 100 = 1000万美元日成交额。
"""
from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from universe import INDEX_TICKERS, get_scan_universe

ACCOUNT_USD = 100_000.0
MIN_DOLLAR_VOLUME = ACCOUNT_USD * 100  # 10,000,000
DEFAULT_RISK_PCT = 0.005  # 0.5%
MAX_OVERNIGHT_PCT = 0.30  # 30%
TYPICAL_SIZE_LOW = 0.10
TYPICAL_SIZE_HIGH = 0.15


def _pct(a: float, b: float) -> float | None:
    if b is None or b == 0 or a is None or (isinstance(a, float) and math.isnan(a)):
        return None
    return (a / b - 1.0) * 100.0


def _safe_float(x) -> float | None:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def fetch_history(ticker: str, period: str = "1y") -> pd.DataFrame | None:
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, auto_adjust=True)
        if df is None or df.empty:
            return None
        df = df.rename(columns=str.title)
        # Yahoo 偶发给出 OHLC 全为空、仅有 Volume 的末日 K 线，丢弃以免最新价变 NaN
        if "Close" in df.columns:
            df = df.dropna(subset=["Close"])
        if df.empty or len(df) < 50:
            return None
        return df
    except Exception:
        return None


def fetch_name(ticker: str) -> str:
    try:
        info = yf.Ticker(ticker).info or {}
        return info.get("shortName") or info.get("longName") or ticker
    except Exception:
        return ticker


def analyze_ticker(ticker: str, hist: pd.DataFrame | None = None) -> dict[str, Any] | None:
    if hist is None:
        hist = fetch_history(ticker)
    if hist is None or len(hist) < 50:
        return None

    close = hist["Close"].astype(float)
    high = hist["High"].astype(float)
    low = hist["Low"].astype(float)
    volume = hist["Volume"].astype(float)

    last = float(close.iloc[-1])
    if last != last or last <= 0:  # NaN or non-positive
        return None

    # 日成交额（近20日均值）
    dollar_vol = (close * volume).tail(20).mean()
    dollar_vol = _safe_float(dollar_vol)
    if dollar_vol is None:
        return None

    # 涨幅：约 21 / 63 / 126 交易日
    def ret(n: int) -> float | None:
        if len(close) <= n:
            return None
        return _pct(last, float(close.iloc[-n - 1]))

    r1 = ret(21)
    r3 = ret(63)
    r6 = ret(126)

    # 均线
    ma10 = float(close.tail(10).mean()) if len(close) >= 10 else None
    ma20 = float(close.tail(20).mean()) if len(close) >= 20 else None
    dist_ma10 = _pct(last, ma10) if ma10 else None
    dist_ma20 = _pct(last, ma20) if ma20 else None

    # ADR%：20日平均振幅 (High-Low)/Close
    adr = ((high - low) / close * 100).tail(20).mean()
    adr = _safe_float(adr)

    # 结构：前期大涨 30–100%+（看近 3 月内最高相对此前低点）
    prior_big_move = False
    consol = False
    near_ma = False
    near_breakout = False

    if len(close) >= 80:
        # 过去约 3 个月窗口内最大涨幅
        window = close.iloc[-90:-20] if len(close) >= 90 else close.iloc[:-20]
        if len(window) >= 20:
            w_low = float(window.min())
            w_high = float(window.max())
            move = _pct(w_high, w_low)
            if move is not None and move >= 30:
                prior_big_move = True

        # 盘整：近 10–40 日价格区间相对收窄
        recent = close.tail(30)
        if len(recent) >= 20:
            rng = (float(recent.max()) - float(recent.min())) / last * 100
            if 2 <= rng <= 25:  # 约 2 周–2 月常见盘整幅度软判断
                consol = True

    # 贴近上升均线
    if (
        ma10
        and ma20
        and ma10 > ma20
        and dist_ma10 is not None
        and dist_ma20 is not None
        and abs(dist_ma10) <= 8
        and abs(dist_ma20) <= 12
        and last >= ma20 * 0.97
    ):
        near_ma = True

    # 接近突破：价格接近近 20–40 日高点
    if len(high) >= 40:
        hh = float(high.tail(40).max())
        if last >= hh * 0.97:
            near_breakout = True

    day_low = float(low.iloc[-1])
    # 止损：日低 或 入场价 − 1×ADR
    stop_day_low = day_low
    stop_adr = last - (adr / 100.0 * last) if adr else day_low
    stop = min(stop_day_low, stop_adr) if stop_adr else stop_day_low
    if stop >= last:
        stop = last * 0.95  # 兜底 5%

    risk_usd = ACCOUNT_USD * DEFAULT_RISK_PCT  # 500
    risk_per_share = last - stop
    shares_by_risk = int(risk_usd / risk_per_share) if risk_per_share > 0 else 0
    max_shares_overnight = int((ACCOUNT_USD * MAX_OVERNIGHT_PCT) / last)
    typical_shares_low = int((ACCOUNT_USD * TYPICAL_SIZE_LOW) / last)
    typical_shares_high = int((ACCOUNT_USD * TYPICAL_SIZE_HIGH) / last)
    suggested = min(shares_by_risk, max_shares_overnight)
    if typical_shares_high > 0:
        suggested = min(suggested, typical_shares_high)

    return {
        "代码": ticker,
        "名称": ticker,  # 稍后批量补全
        "1月涨幅": round(r1, 2) if r1 is not None else None,
        "3月涨幅": round(r3, 2) if r3 is not None else None,
        "6月涨幅": round(r6, 2) if r6 is not None else None,
        "日成交额": round(dollar_vol, 0),
        "20日平均振幅%": round(adr, 2) if adr is not None else None,
        "距10日均线%": round(dist_ma10, 2) if dist_ma10 is not None else None,
        "距20日均线%": round(dist_ma20, 2) if dist_ma20 is not None else None,
        "是否贴近均线盘整": bool(near_ma and consol),
        "前期大涨": prior_big_move,
        "盘整": consol,
        "贴近均线": near_ma,
        "接近突破": near_breakout,
        "最新价": round(last, 2),
        "建议止损": round(stop, 2),
        "建议仓位股数示例": suggested,
        "按风险股数": shares_by_risk,
        "隔夜上限股数": max_shares_overnight,
        "典型仓位股数区间": f"{typical_shares_low}–{typical_shares_high}",
    }


def score_rs(row: dict, p1: float, p3: float, p6: float) -> float:
    """相对强度综合分：越高越强。用百分位加权。"""
    s = 0.0
    w = 0.0
    for key, pct, weight in (
        ("1月涨幅", p1, 0.45),
        ("3月涨幅", p3, 0.35),
        ("6月涨幅", p6, 0.20),
    ):
        v = row.get(key)
        if v is None:
            continue
        s += pct * weight
        w += weight
    return s / w if w > 0 else 0.0


def percentile_rank(series: pd.Series) -> pd.Series:
    return series.rank(pct=True, method="average") * 100


def get_market_filter() -> dict[str, Any]:
    """纳斯达克代理：QQQ 相对 10/20 日均线。"""
    try:
        df = fetch_history("QQQ", period="3mo")
        if df is None:
            return {"可用": False, "说明": "无法获取 QQQ 数据"}
        close = df["Close"].astype(float).dropna()
        if len(close) < 20:
            return {"可用": False, "说明": "QQQ 有效收盘价不足"}
        last = float(close.iloc[-1])
        ma10 = float(close.tail(10).mean())
        ma20 = float(close.tail(20).mean())
        above = last > ma10 and last > ma20 and ma10 >= ma20
        return {
            "可用": True,
            "标的": "纳斯达克100代理",
            "最新价": round(last, 2),
            "10日均线": round(ma10, 2),
            "20日均线": round(ma20, 2),
            "绿色区域": above,
            "说明": "价格在 10/20 日均线上方且均线向上 → 绿色进攻区" if above else "未同时站上 10/20 日均线 → 谨慎",
        }
    except Exception as e:
        return {"可用": False, "说明": str(e)}


def run_screen(
    min_adr: float | None = None,
    top_pct: float = 2.0,
    require_structure: bool = False,
    max_workers: int = 12,
    progress_cb=None,
) -> dict[str, Any]:
    tickers = get_scan_universe()
    rows: list[dict] = []
    errors = 0
    total = len(tickers)
    done = 0

    # 批量下载加速
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
                # 单标的情况
                sub = data.dropna(how="all")
            if sub is None or sub.empty:
                return None
            sub = sub.rename(columns=str.title)
            if "Close" in sub.columns:
                sub = sub.dropna(subset=["Close"])
            if sub.empty or len(sub) < 50:
                return None
            return sub
        except Exception:
            return fetch_history(t)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(analyze_ticker, t, hist_for(t)): t for t in tickers}
        for fut in as_completed(futs):
            done += 1
            if progress_cb and done % 20 == 0:
                progress_cb(done, total)
            try:
                r = fut.result()
                if r:
                    rows.append(r)
                else:
                    errors += 1
            except Exception:
                errors += 1

    if not rows:
        return {
            "更新时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "时区": "Asia/Shanghai",
            "市场过滤": get_market_filter(),
            "结果": [],
            "统计": {"扫描数": total, "有效": 0, "失败": errors},
        }

    df = pd.DataFrame(rows)

    # 流动性硬过滤
    df = df[df["日成交额"] >= MIN_DOLLAR_VOLUME].copy()

    # 可选 ADR 软过滤
    if min_adr is not None and min_adr > 0:
        df = df[df["20日平均振幅%"].fillna(0) >= min_adr].copy()

    if df.empty:
        return {
            "更新时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "时区": "Asia/Shanghai",
            "市场过滤": get_market_filter(),
            "结果": [],
            "统计": {"扫描数": total, "有效": 0, "失败": errors, "流动性后": 0},
        }

    # 相对强度百分位
    for col in ("1月涨幅", "3月涨幅", "6月涨幅"):
        df[f"{col}_百分位"] = percentile_rank(df[col].fillna(-999))

    # 取各周期前 top_pct%，或综合分交集倾向
    # 相对强度：综合得分；入选 = 任一周期进入前 top_pct%（默认2%）或综合分进入前约8%
    # 表格按 RS 分排序，最强者即「前1–2%」核心观察对象
    thr = 100 - top_pct
    df["RS分"] = (
        df["1月涨幅_百分位"] * 0.45
        + df["3月涨幅_百分位"] * 0.35
        + df["6月涨幅_百分位"] * 0.20
    )
    in_top = (
        (df["1月涨幅_百分位"] >= thr)
        | (df["3月涨幅_百分位"] >= thr)
        | (df["6月涨幅_百分位"] >= thr)
    )
    rs_thr = df["RS分"].quantile(0.92) if len(df) >= 20 else df["RS分"].median()
    df = df[in_top | (df["RS分"] >= rs_thr)].copy()

    if require_structure:
        df = df[df["是否贴近均线盘整"] | df["接近突破"]].copy()

    df = df.sort_values("RS分", ascending=False)

    # 补名称（限前 80，避免过慢）
    names = {}
    top_n = df.head(80)
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_name, t): t for t in top_n["代码"].tolist()}
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                names[t] = fut.result()
            except Exception:
                names[t] = t
    df["名称"] = df["代码"].map(lambda x: names.get(x, x))

    # 输出列
    out_cols = [
        "代码", "名称", "最新价",
        "1月涨幅", "3月涨幅", "6月涨幅",
        "日成交额", "20日平均振幅%",
        "距10日均线%", "距20日均线%",
        "是否贴近均线盘整", "前期大涨", "盘整", "贴近均线", "接近突破",
        "建议止损", "建议仓位股数示例", "典型仓位股数区间", "RS分",
    ]
    records = df[out_cols].replace({np.nan: None}).to_dict(orient="records")
    for r in records:
        r["RS分"] = round(float(r["RS分"]), 1) if r.get("RS分") is not None else None
        if r.get("日成交额") is not None:
            r["日成交额"] = int(r["日成交额"])
        for b in ("是否贴近均线盘整", "前期大涨", "盘整", "贴近均线", "接近突破"):
            r[b] = bool(r.get(b))

    return {
        "更新时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "时区": "Asia/Shanghai",
        "账户美元": ACCOUNT_USD,
        "流动性门槛美元": MIN_DOLLAR_VOLUME,
        "风险默认美元": ACCOUNT_USD * DEFAULT_RISK_PCT,
        "市场过滤": get_market_filter(),
        "结果": records,
        "统计": {
            "扫描数": total,
            "有效分析": len(rows),
            "失败": errors,
            "流动性后": int((pd.DataFrame(rows)["日成交额"] >= MIN_DOLLAR_VOLUME).sum()) if rows else 0,
            "入选": len(records),
            "相对强度阈值百分位": top_pct,
            "最低振幅过滤": min_adr,
        },
    }


if __name__ == "__main__":
    t0 = time.time()
    print("开始筛选…")
    res = run_screen(min_adr=4.0)
    print(f"完成，用时 {time.time()-t0:.1f}s，入选 {res['统计']['入选']}")
    for r in res["结果"][:10]:
        print(r["代码"], r.get("1月涨幅"), r.get("RS分"), r.get("建议仓位股数示例"))
