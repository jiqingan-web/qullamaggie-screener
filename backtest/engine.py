"""组合回测引擎：风险仓位、分批止盈、均线跟踪。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np
import pandas as pd

from .config import (
    ACCOUNT_USD,
    COMMISSION_BPS,
    MAX_OPEN_POSITIONS,
    MAX_OVERNIGHT_PCT,
    PARTIAL_EXIT_DAYS,
    PARTIAL_EXIT_FRAC,
    RISK_PCT,
    RS_REBALANCE_DAYS,
    SLIPPAGE_BPS,
    TYPICAL_SIZE_HIGH,
    USE_MARKET_FILTER,
)
from .signals import is_breakout_entry, market_green, rs_candidates_on_date, stop_price, trail_exit_signal


@dataclass
class Position:
    ticker: str
    shares: float
    entry_price: float
    entry_date: str
    stop: float
    days_held: int = 0
    partial_done: bool = False
    remaining_frac: float = 1.0


@dataclass
class Trade:
    代码: str
    方向: str
    日期: str
    价格: float
    股数: float
    原因: str
    盈亏美元: float = 0.0


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: list[Trade]
    stats: dict[str, Any]
    daily: pd.DataFrame


def _cost(notional: float) -> float:
    return abs(notional) * (COMMISSION_BPS + SLIPPAGE_BPS) / 10_000.0


def position_size(equity: float, entry: float, stop: float) -> int:
    risk_usd = equity * RISK_PCT
    per_share = entry - stop
    if per_share <= 0 or entry <= 0:
        return 0
    by_risk = int(risk_usd / per_share)
    by_overnight = int((equity * MAX_OVERNIGHT_PCT) / entry)
    by_typical = int((equity * TYPICAL_SIZE_HIGH) / entry)
    return max(0, min(by_risk, by_overnight, by_typical))


def run_backtest(
    panels: dict[str, pd.DataFrame],
    market: pd.DataFrame | None,
    start: str | None = None,
    end: str | None = None,
    initial_cash: float = ACCOUNT_USD,
    use_market_filter: bool = USE_MARKET_FILTER,
) -> BacktestResult:
    # 交易日历：取所有标的日期并集再与市场对齐
    all_dates = sorted(set().union(*[set(df.index) for df in panels.values()]))
    if market is not None:
        mgreen = market_green(market)
        all_dates = [d for d in all_dates if d in market.index]
    else:
        mgreen = None
        use_market_filter = False

    all_dates = pd.DatetimeIndex(all_dates)
    if start:
        all_dates = all_dates[all_dates >= pd.Timestamp(start)]
    if end:
        all_dates = all_dates[all_dates <= pd.Timestamp(end)]
    # 需要足够预热
    if len(all_dates) < 150:
        empty = pd.Series(dtype=float)
        return BacktestResult(empty, [], {"错误": "有效交易日不足"}, pd.DataFrame())

    cash = float(initial_cash)
    positions: dict[str, Position] = {}
    trades: list[Trade] = []
    equity_curve: list[tuple[pd.Timestamp, float]] = []
    candidates: set[str] = set()
    last_rs_i = -999

    def mark_to_market(dt: pd.Timestamp) -> float:
        eq = cash
        for t, pos in positions.items():
            df = panels.get(t)
            if df is None or dt not in df.index:
                eq += pos.shares * pos.entry_price
            else:
                eq += pos.shares * float(df.loc[dt, "Close"])
        return eq

    def close_shares(t: str, pos: Position, dt: pd.Timestamp, px: float, shares: float, reason: str):
        nonlocal cash
        if shares <= 0:
            return
        proceeds = shares * px
        cash += proceeds - _cost(proceeds)
        pnl = (px - pos.entry_price) * shares
        trades.append(
            Trade(
                代码=t,
                方向="卖出",
                日期=str(dt.date()),
                价格=round(px, 4),
                股数=round(shares, 4),
                原因=reason,
                盈亏美元=round(pnl, 2),
            )
        )
        pos.shares -= shares
        if pos.shares < 1e-6:
            positions.pop(t, None)

    for i, dt in enumerate(all_dates):
        # --- 先处理持仓：止损 / 分批 / 跟踪 ---
        for t in list(positions.keys()):
            pos = positions[t]
            df = panels.get(t)
            if df is None or dt not in df.index:
                continue
            row = df.loc[dt]
            low = float(row["Low"])
            high = float(row["High"])
            close = float(row["Close"])
            pos.days_held += 1

            # 止损：当日低触及
            if low <= pos.stop:
                fill = min(pos.stop, float(row["Open"]))  # 跳空则按开盘
                if float(row["Open"]) < pos.stop:
                    fill = float(row["Open"])
                else:
                    fill = pos.stop
                close_shares(t, pos, dt, fill, pos.shares, "止损")
                continue

            # 分批：持有 PARTIAL_EXIT_DAYS 后卖出一部分
            if not pos.partial_done and pos.days_held >= PARTIAL_EXIT_DAYS:
                sell = pos.shares * PARTIAL_EXIT_FRAC
                close_shares(t, pos, dt, close, sell, f"分批止盈({PARTIAL_EXIT_DAYS}日)")
                if t in positions:
                    positions[t].partial_done = True
                    positions[t].remaining_frac = 1.0 - PARTIAL_EXIT_FRAC
                continue

            # 跟踪：收盘跌破 10 日均线
            if pos.partial_done or pos.days_held >= PARTIAL_EXIT_DAYS:
                if trail_exit_signal(row):
                    close_shares(t, pos, dt, close, pos.shares, "跌破10日均线")
                    continue

        # --- RS 候选再平衡 ---
        if i - last_rs_i >= RS_REBALANCE_DAYS:
            candidates = rs_candidates_on_date(panels, dt)
            last_rs_i = i

        # --- 市场过滤 ---
        allow_entry = True
        if use_market_filter and mgreen is not None and dt in mgreen.index:
            allow_entry = bool(mgreen.loc[dt])

        # --- 开仓 ---
        if allow_entry and len(positions) < MAX_OPEN_POSITIONS:
            eq = mark_to_market(dt)
            # 按当日涨幅强度排序候选
            ranked = []
            for t in candidates:
                if t in positions:
                    continue
                df = panels.get(t)
                if df is None or dt not in df.index:
                    continue
                row = df.loc[dt]
                if not is_breakout_entry(row):
                    continue
                ranked.append((t, float(row.get("ret_1m") or 0), row))
            ranked.sort(key=lambda x: x[1], reverse=True)
            for t, _, row in ranked:
                if len(positions) >= MAX_OPEN_POSITIONS:
                    break
                entry = float(row["Close"])  # 日线近似：收盘确认突破后次日更佳；此处用收盘成交简化
                day_low = float(row["Low"])
                adr = row.get("adr20")
                adr_v = float(adr) if adr is not None and not pd.isna(adr) else None
                stp = stop_price(entry, day_low, adr_v)
                shares = position_size(eq, entry, stp)
                if shares <= 0:
                    continue
                notional = shares * entry
                if notional + _cost(notional) > cash:
                    shares = int(cash / (entry * (1 + (COMMISSION_BPS + SLIPPAGE_BPS) / 10_000)))
                    if shares <= 0:
                        continue
                    notional = shares * entry
                cash -= notional + _cost(notional)
                positions[t] = Position(
                    ticker=t,
                    shares=float(shares),
                    entry_price=entry,
                    entry_date=str(dt.date()),
                    stop=stp,
                )
                trades.append(
                    Trade(
                        代码=t,
                        方向="买入",
                        日期=str(dt.date()),
                        价格=round(entry, 4),
                        股数=float(shares),
                        原因="突破开仓",
                        盈亏美元=0.0,
                    )
                )
                eq = mark_to_market(dt)

        equity_curve.append((dt, mark_to_market(dt)))

    # 期末平仓
    if all_dates is not None and len(all_dates) > 0:
        dt = all_dates[-1]
        for t in list(positions.keys()):
            pos = positions[t]
            df = panels.get(t)
            px = float(df.loc[dt, "Close"]) if df is not None and dt in df.index else pos.entry_price
            close_shares(t, pos, dt, px, pos.shares, "回测结束平仓")

    eq_s = pd.Series({d: v for d, v in equity_curve}).sort_index()
    stats = compute_stats(eq_s, trades, initial_cash)
    daily = pd.DataFrame({"权益": eq_s})
    daily["回撤"] = eq_s / eq_s.cummax() - 1.0
    return BacktestResult(equity=eq_s, trades=trades, stats=stats, daily=daily)


def compute_stats(equity: pd.Series, trades: list[Trade], initial: float) -> dict[str, Any]:
    if equity.empty:
        return {"错误": "无权益曲线"}
    final = float(equity.iloc[-1])
    days = (equity.index[-1] - equity.index[0]).days
    years = max(days / 365.25, 1e-6)
    cagr = (final / initial) ** (1 / years) - 1.0
    dd = equity / equity.cummax() - 1.0
    max_dd = float(dd.min())

    # 按完整回合：买入到对应卖出聚合
    sells = [t for t in trades if t.方向 == "卖出"]
    wins = [t for t in sells if t.盈亏美元 > 0]
    losses = [t for t in sells if t.盈亏美元 <= 0]
    gross_profit = sum(t.盈亏美元 for t in wins) if wins else 0.0
    gross_loss = abs(sum(t.盈亏美元 for t in losses)) if losses else 0.0
    pf = (gross_profit / gross_loss) if gross_loss > 1e-9 else (999.0 if gross_profit > 0 else 0.0)
    n_sells = len(sells)
    win_rate = len(wins) / n_sells if n_sells else 0.0
    n_entries = sum(1 for t in trades if t.方向 == "买入")

    return {
        "初始资金美元": initial,
        "期末资金美元": round(final, 2),
        "累计收益%": round((final / initial - 1.0) * 100, 2),
        "年化收益CAGR%": round(cagr * 100, 2),
        "最大回撤%": round(max_dd * 100, 2),
        "胜率%": round(win_rate * 100, 2),
        "盈亏比_利润因子": round(pf, 3),
        "买入笔数": n_entries,
        "卖出笔数": n_sells,
        "盈利卖出笔数": len(wins),
        "亏损卖出笔数": len(losses),
        "起始日": str(equity.index[0].date()),
        "结束日": str(equity.index[-1].date()),
        "交易日数": int(len(equity)),
    }


def trades_to_records(trades: list[Trade]) -> list[dict]:
    return [asdict(t) for t in trades]
