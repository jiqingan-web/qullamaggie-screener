"""纸面经纪：状态持久化 + 按 last_scan / 最新行情模拟成交。"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.config import (  # noqa: E402
    ACCOUNT_USD,
    MAX_OVERNIGHT_PCT,
    PARTIAL_EXIT_DAYS,
    PARTIAL_EXIT_FRAC,
    RISK_PCT,
    TYPICAL_SIZE_HIGH,
)
from backtest.signals import stop_price, trail_exit_signal  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")
STATE_PATH = Path(__file__).resolve().parent / "state" / "paper_state.json"
DEFAULT_SCAN = ROOT / "data" / "last_scan.json"


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def default_state() -> dict[str, Any]:
    return {
        "账户美元": ACCOUNT_USD,
        "现金美元": ACCOUNT_USD,
        "持仓": [],  # {代码, 股数, 成本价, 入场日, 止损, 持有天数, 已分批}
        "成交记录": [],
        "权益曲线": [],
        "上次运行": None,
        "说明": "纸面模拟，非真实经纪商",
    }


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        st = default_state()
        save_state(st, path)
        return st
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_last_bar(ticker: str) -> dict[str, float] | None:
    try:
        df = yf.Ticker(ticker).history(period="1mo", auto_adjust=True)
        if df is None or df.empty:
            return None
        df = df.rename(columns=str.title)
        last = df.iloc[-1]
        close = df["Close"].astype(float)
        return {
            "Open": float(last["Open"]),
            "High": float(last["High"]),
            "Low": float(last["Low"]),
            "Close": float(last["Close"]),
            "ma10": float(close.tail(10).mean()),
            "adr20": float(((df["High"] - df["Low"]) / df["Close"] * 100).tail(20).mean()),
        }
    except Exception:
        return None


def _position_size(equity: float, entry: float, stop: float) -> int:
    risk_usd = equity * RISK_PCT
    per = entry - stop
    if per <= 0 or entry <= 0:
        return 0
    by_risk = int(risk_usd / per)
    by_ov = int((equity * MAX_OVERNIGHT_PCT) / entry)
    by_typ = int((equity * TYPICAL_SIZE_HIGH) / entry)
    return max(0, min(by_risk, by_ov, by_typ))


def _equity(state: dict, marks: dict[str, float]) -> float:
    eq = float(state["现金美元"])
    for p in state["持仓"]:
        px = marks.get(p["代码"], p["成本价"])
        eq += float(p["股数"]) * float(px)
    return eq


def load_signals(scan_path: Path = DEFAULT_SCAN) -> list[dict]:
    if not scan_path.exists():
        return []
    data = json.loads(scan_path.read_text(encoding="utf-8"))
    rows = data.get("结果") or []
    # 优先结构好的：贴近均线盘整或接近突破
    preferred = [r for r in rows if r.get("是否贴近均线盘整") or r.get("接近突破")]
    return preferred or rows[:15]


def run_once(scan_path: Path = DEFAULT_SCAN, state_path: Path = STATE_PATH) -> dict[str, Any]:
    """读取最新信号，更新持仓（止损/分批/跟踪），并对新信号模拟开仓。"""
    state = load_state(state_path)
    held = {p["代码"] for p in state["持仓"]}
    marks: dict[str, float] = {}

    # 更新既有持仓
    still: list[dict] = []
    for pos in state["持仓"]:
        t = pos["代码"]
        bar = _fetch_last_bar(t)
        if bar is None:
            still.append(pos)
            continue
        marks[t] = bar["Close"]
        pos["持有天数"] = int(pos.get("持有天数") or 0) + 1
        # 止损
        if bar["Low"] <= float(pos["止损"]):
            fill = min(float(pos["止损"]), bar["Open"]) if bar["Open"] < float(pos["止损"]) else float(pos["止损"])
            if bar["Open"] < float(pos["止损"]):
                fill = bar["Open"]
            shares = float(pos["股数"])
            state["现金美元"] = float(state["现金美元"]) + shares * fill
            pnl = (fill - float(pos["成本价"])) * shares
            state["成交记录"].append(
                {
                    "时间": _now(),
                    "代码": t,
                    "方向": "卖出",
                    "价格": round(fill, 4),
                    "股数": shares,
                    "原因": "止损",
                    "盈亏美元": round(pnl, 2),
                }
            )
            continue
        # 分批
        if not pos.get("已分批") and pos["持有天数"] >= PARTIAL_EXIT_DAYS:
            sell = float(pos["股数"]) * PARTIAL_EXIT_FRAC
            state["现金美元"] = float(state["现金美元"]) + sell * bar["Close"]
            pnl = (bar["Close"] - float(pos["成本价"])) * sell
            state["成交记录"].append(
                {
                    "时间": _now(),
                    "代码": t,
                    "方向": "卖出",
                    "价格": round(bar["Close"], 4),
                    "股数": round(sell, 4),
                    "原因": f"分批止盈({PARTIAL_EXIT_DAYS}日)",
                    "盈亏美元": round(pnl, 2),
                }
            )
            pos["股数"] = float(pos["股数"]) - sell
            pos["已分批"] = True
        # 跟踪
        row_like = {"Close": bar["Close"], "ma10": bar["ma10"]}
        if pos.get("已分批") and trail_exit_signal(row_like):
            shares = float(pos["股数"])
            state["现金美元"] = float(state["现金美元"]) + shares * bar["Close"]
            pnl = (bar["Close"] - float(pos["成本价"])) * shares
            state["成交记录"].append(
                {
                    "时间": _now(),
                    "代码": t,
                    "方向": "卖出",
                    "价格": round(bar["Close"], 4),
                    "股数": shares,
                    "原因": "跌破10日均线",
                    "盈亏美元": round(pnl, 2),
                }
            )
            continue
        still.append(pos)

    state["持仓"] = still
    held = {p["代码"] for p in state["持仓"]}

    # 新开仓：来自 last_scan
    signals = load_signals(scan_path)
    eq = _equity(state, marks)
    for sig in signals:
        t = sig.get("代码")
        if not t or t in held:
            continue
        if len(state["持仓"]) >= 8:
            break
        # 结构过滤：需要盘整或接近突破
        if not (sig.get("是否贴近均线盘整") or sig.get("接近突破") or sig.get("贴近均线")):
            continue
        bar = _fetch_last_bar(t)
        if bar is None:
            continue
        entry = bar["Close"]
        marks[t] = entry
        suggested_stop = sig.get("建议止损")
        stp = float(suggested_stop) if suggested_stop else stop_price(entry, bar["Low"], bar.get("adr20"))
        if stp >= entry:
            stp = stop_price(entry, bar["Low"], bar.get("adr20"))
        shares = _position_size(eq, entry, stp)
        cost = shares * entry
        if shares <= 0 or cost > float(state["现金美元"]):
            continue
        state["现金美元"] = float(state["现金美元"]) - cost
        state["持仓"].append(
            {
                "代码": t,
                "名称": sig.get("名称") or t,
                "股数": float(shares),
                "成本价": round(entry, 4),
                "入场日": _now()[:10],
                "止损": round(stp, 4),
                "持有天数": 0,
                "已分批": False,
            }
        )
        state["成交记录"].append(
            {
                "时间": _now(),
                "代码": t,
                "方向": "买入",
                "价格": round(entry, 4),
                "股数": float(shares),
                "原因": "信号开仓",
                "盈亏美元": 0.0,
            }
        )
        held.add(t)
        eq = _equity(state, marks)

    eq = _equity(state, marks)
    state["上次运行"] = _now()
    state["权益曲线"].append({"时间": _now(), "权益美元": round(eq, 2)})
    # 只保留最近 500 点
    state["权益曲线"] = state["权益曲线"][-500:]
    state["成交记录"] = state["成交记录"][-500:]
    save_state(state, state_path)
    return {
        "时间": state["上次运行"],
        "现金美元": round(float(state["现金美元"]), 2),
        "权益美元": round(eq, 2),
        "持仓数": len(state["持仓"]),
        "持仓": state["持仓"],
        "信号数": len(signals),
    }


def status(state_path: Path = STATE_PATH) -> dict[str, Any]:
    state = load_state(state_path)
    marks: dict[str, float] = {}
    for p in state["持仓"]:
        bar = _fetch_last_bar(p["代码"])
        if bar:
            marks[p["代码"]] = bar["Close"]
    eq = _equity(state, marks)
    pos_view = []
    for p in state["持仓"]:
        m = marks.get(p["代码"], p["成本价"])
        pos_view.append(
            {
                **p,
                "现价": round(float(m), 4),
                "浮动盈亏美元": round((float(m) - float(p["成本价"])) * float(p["股数"]), 2),
            }
        )
    return {
        "上次运行": state.get("上次运行"),
        "现金美元": round(float(state["现金美元"]), 2),
        "权益美元": round(eq, 2),
        "持仓": pos_view,
        "最近成交": state.get("成交记录", [])[-10:],
    }
