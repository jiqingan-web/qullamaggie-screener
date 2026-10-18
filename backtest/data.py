"""行情下载与本地缓存（yfinance）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

from .config import CACHE_DIR, MARKET_TICKER

# 保证可从仓库根导入 universe
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _cache_path(ticker: str, start: str, end: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = ticker.replace("/", "-")
    return CACHE_DIR / f"{safe}_{start}_{end}.parquet"


def download_ticker(ticker: str, start: str, end: str, force: bool = False) -> pd.DataFrame | None:
    path = _cache_path(ticker, start, end)
    if path.exists() and not force:
        try:
            df = pd.read_parquet(path)
            if not df.empty and len(df) >= 30:
                return df
        except Exception:
            pass
    try:
        df = yf.download(
            ticker,
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.rename(columns=str.title)
        need = {"Open", "High", "Low", "Close", "Volume"}
        if not need.issubset(set(df.columns)):
            return None
        df = df[list(need)].dropna(how="any")
        if len(df) < 30:
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        try:
            df.to_parquet(path)
        except Exception:
            df.to_csv(path.with_suffix(".csv"))
        return df
    except Exception:
        return None


def download_many(
    tickers: list[str],
    start: str,
    end: str,
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    """批量下载；优先单标的缓存，缺失时用 yf.download 批量补齐。"""
    out: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for t in tickers:
        path = _cache_path(t, start, end)
        if path.exists() and not force:
            try:
                df = pd.read_parquet(path)
                if not df.empty and len(df) >= 30:
                    out[t] = df
                    continue
            except Exception:
                pass
        missing.append(t)

    if not missing:
        return out

    # 分批批量下载加速
    batch = 40
    for i in range(0, len(missing), batch):
        chunk = missing[i : i + batch]
        try:
            raw = yf.download(
                chunk,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
                threads=True,
                group_by="ticker",
            )
        except Exception:
            raw = None
        if raw is None or raw.empty:
            for t in chunk:
                df = download_ticker(t, start, end, force=force)
                if df is not None:
                    out[t] = df
            continue
        for t in chunk:
            try:
                if len(chunk) == 1:
                    sub = raw.copy()
                elif isinstance(raw.columns, pd.MultiIndex):
                    if t not in raw.columns.get_level_values(0):
                        continue
                    sub = raw[t].copy()
                else:
                    sub = raw.copy()
                sub = sub.rename(columns=str.title).dropna(how="all")
                need = {"Open", "High", "Low", "Close", "Volume"}
                if not need.issubset(set(sub.columns)):
                    continue
                sub = sub[list(need)].dropna(how="any")
                if len(sub) < 30:
                    continue
                sub.index = pd.to_datetime(sub.index).tz_localize(None)
                path = _cache_path(t, start, end)
                try:
                    sub.to_parquet(path)
                except Exception:
                    sub.to_csv(path.with_suffix(".csv"))
                out[t] = sub
            except Exception:
                df = download_ticker(t, start, end, force=force)
                if df is not None:
                    out[t] = df
    return out


def load_market(start: str, end: str, force: bool = False) -> pd.DataFrame | None:
    return download_ticker(MARKET_TICKER, start, end, force=force)


def resolve_tickers(full: bool = False) -> list[str]:
    from .config import SAMPLE_TICKERS

    if not full:
        return list(SAMPLE_TICKERS)
    from universe import get_scan_universe

    return get_scan_universe()
