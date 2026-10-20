"""TOP5 纸面组合：按 data/top5.json 建议仓位建仓，每日更新标记价与盈亏。

用法：
  python -m paper.portfolio_top5 update   # 刷新行情、计算盈亏；无状态则从 top5 初始化
  python -m paper.portfolio_top5 report   # 打印中文摘要（并写 data/pnl_latest.md）
  python -m paper.portfolio_top5 init     # 强制用最新 top5 重建账本（覆盖现有）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_TOP5 = ROOT / "data" / "top5.json"
DEFAULT_STATE = ROOT / "data" / "portfolio_top5.json"
DEFAULT_REPORT = ROOT / "data" / "pnl_latest.md"
ACCOUNT_USD = 100_000.0


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_marks(tickers: list[str]) -> dict[str, float]:
    """用 yfinance 拉取最新价；失败时返回空 dict（调用方回退成本价）。

    优先 fast_info.lastPrice（当日/盘后更及时）；Yahoo 偶发给出 OHLC 为空的末日 K 线，
    history 有效收盘可能仍停在上一完整交易日。
    """
    import yfinance as yf

    marks: dict[str, float] = {}
    if not tickers:
        return marks

    for t in tickers:
        px = None
        try:
            fi = yf.Ticker(t).fast_info
            for key in ("lastPrice", "previousClose", "regularMarketPreviousClose"):
                lp = fi.get(key)
                if lp is not None:
                    cand = float(lp)
                    if cand == cand and cand > 0:
                        px = cand
                        break
            if px is None:
                hist = yf.Ticker(t).history(period="5d", auto_adjust=True)
                if hist is not None and not hist.empty:
                    closes = hist["Close"].dropna()
                    if not closes.empty:
                        px = float(closes.iloc[-1])
        except Exception:
            px = None
        if px is not None and px == px and px > 0:
            marks[t] = round(px, 4)
    return marks


def _positions_from_top5(top5: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    """按建议股数与最新价开仓；返回 (持仓列表, 占用市值)。"""
    cash_used = 0.0
    positions: list[dict[str, Any]] = []
    for row in top5.get("结果", [])[:5]:
        ticker = str(row["代码"])
        name = str(row.get("名称") or ticker)
        shares = int(row.get("建议仓位股数") or 0)
        entry = float(row.get("最新价") or 0)
        stop = row.get("建议止损")
        rank = row.get("排名")
        if shares <= 0 or entry <= 0:
            continue
        cost = round(shares * entry, 2)
        cash_used += cost
        positions.append(
            {
                "代码": ticker,
                "名称": name,
                "股数": shares,
                "成本价": round(entry, 4),
                "标记价": round(entry, 4),
                "市值美元": cost,
                "盈亏美元": 0.0,
                "盈亏%": 0.0,
                "建议止损": float(stop) if stop is not None else None,
                "排名": rank,
                "开仓时间": top5.get("更新时间") or _now(),
            }
        )
    return positions, cash_used


def init_state(
    top5_path: Path = DEFAULT_TOP5,
    state_path: Path = DEFAULT_STATE,
    force: bool = False,
) -> dict[str, Any]:
    if state_path.exists() and not force:
        return _load_json(state_path)
    if not top5_path.exists():
        raise FileNotFoundError(f"找不到 TOP5 文件：{top5_path}")
    top5 = _load_json(top5_path)
    account = float(top5.get("账户美元") or ACCOUNT_USD)
    positions, cash_used = _positions_from_top5(top5)
    members = [p["代码"] for p in positions]
    state: dict[str, Any] = {
        "账户美元": account,
        "现金美元": round(account - cash_used, 2),
        "持仓": positions,
        "持仓代码": members,
        "上次TOP5代码": members,
        "上次更新": _now(),
        "建仓时间": _now(),
        "来源TOP5更新时间": top5.get("更新时间"),
        "调仓提示": [],
        "合计": {
            "持仓市值美元": round(cash_used, 2),
            "权益美元": round(account, 2),
            "盈亏美元": 0.0,
            "盈亏%": 0.0,
            "已实现盈亏美元": 0.0,
        },
        "说明": "TOP5 纸面组合：按 top5.json 建议股数开仓，不自动换仓；成员变动只记提示。",
    }
    _save_json(state_path, state)
    return state


def _rebalance_notes(state: dict[str, Any], top5: dict[str, Any] | None) -> list[str]:
    notes: list[str] = []
    if not top5:
        return notes
    new_members = [str(r["代码"]) for r in top5.get("结果", [])[:5]]
    old = list(state.get("上次TOP5代码") or state.get("持仓代码") or [])
    held = {p["代码"] for p in state.get("持仓", [])}
    added = [t for t in new_members if t not in old]
    removed = [t for t in old if t not in new_members]
    still_held_but_out = [t for t in held if t not in new_members]
    if added or removed:
        parts = []
        if added:
            parts.append("新进 " + "、".join(added))
        if removed:
            parts.append("落选 " + "、".join(removed))
        msg = (
            f"{_now()} TOP5 成员变动：{'；'.join(parts)}。"
            "未自动换仓，请人工确认后再调整。"
        )
        if still_held_but_out:
            msg += f" 当前仍持有但已不在 TOP5：{'、'.join(still_held_but_out)}。"
        notes.append(msg)
        hist = list(state.get("调仓提示") or [])
        hist.append(msg)
        state["调仓提示"] = hist[-20:]
    state["上次TOP5代码"] = new_members
    return notes


def _mark_positions(state: dict[str, Any], marks: dict[str, float]) -> None:
    total_mv = 0.0
    total_pnl = 0.0
    for p in state["持仓"]:
        t = p["代码"]
        shares = int(p["股数"])
        cost = float(p["成本价"])
        mark = float(marks.get(t, p.get("标记价") or cost))
        mv = round(shares * mark, 2)
        pnl = round(shares * (mark - cost), 2)
        pct = round((mark / cost - 1.0) * 100.0, 2) if cost > 0 else 0.0
        p["标记价"] = round(mark, 4)
        p["市值美元"] = mv
        p["盈亏美元"] = pnl
        p["盈亏%"] = pct
        total_mv += mv
        total_pnl += pnl
    cash = float(state.get("现金美元") or 0)
    equity = round(cash + total_mv, 2)
    account = float(state.get("账户美元") or ACCOUNT_USD)
    realized = float((state.get("合计") or {}).get("已实现盈亏美元") or 0)
    state["合计"] = {
        "持仓市值美元": round(total_mv, 2),
        "权益美元": equity,
        "盈亏美元": round(total_pnl, 2),
        "盈亏%": round((equity / account - 1.0) * 100.0, 2) if account else 0.0,
        "已实现盈亏美元": realized,
    }
    state["持仓代码"] = [p["代码"] for p in state["持仓"]]
    state["上次更新"] = _now()


def update(
    top5_path: Path = DEFAULT_TOP5,
    state_path: Path = DEFAULT_STATE,
) -> dict[str, Any]:
    if not state_path.exists():
        state = init_state(top5_path, state_path, force=True)
    else:
        state = _load_json(state_path)

    top5 = _load_json(top5_path) if top5_path.exists() else None
    notes = _rebalance_notes(state, top5)

    tickers = [p["代码"] for p in state.get("持仓", [])]
    marks = _fetch_marks(tickers)
    _mark_positions(state, marks)
    if top5:
        state["来源TOP5更新时间"] = top5.get("更新时间")
    _save_json(state_path, state)
    state["_本次调仓提示"] = notes
    return state


def format_report(state: dict[str, Any]) -> str:
    tot = state.get("合计") or {}
    lines: list[str] = []
    lines.append("# TOP5 纸面组合盈亏日报")
    lines.append("")
    lines.append(f"- **更新时间**：{state.get('上次更新')}（Asia/Shanghai）")
    lines.append(f"- **建仓时间**：{state.get('建仓时间')}")
    lines.append(f"- **账户初始**：${float(state.get('账户美元') or 0):,.2f}")
    lines.append(f"- **现金**：${float(state.get('现金美元') or 0):,.2f}")
    lines.append(f"- **持仓市值**：${float(tot.get('持仓市值美元') or 0):,.2f}")
    lines.append(f"- **权益合计**：${float(tot.get('权益美元') or 0):,.2f}")
    pnl = float(tot.get("盈亏美元") or 0)
    pct = float(tot.get("盈亏%") or 0)
    sign = "+" if pnl >= 0 else ""
    lines.append(f"- **浮动盈亏**：{sign}${pnl:,.2f}（{sign}{pct:.2f}%）")
    lines.append("")
    lines.append("## 持仓明细")
    lines.append("")
    lines.append("| 排名 | 代码 | 名称 | 股数 | 成本价 | 标记价 | 市值$ | 盈亏$ | 盈亏% |")
    lines.append("|---:|:---|:---|---:|---:|---:|---:|---:|---:|")
    for p in state.get("持仓", []):
        pp = float(p.get("盈亏美元") or 0)
        pc = float(p.get("盈亏%") or 0)
        s = "+" if pp >= 0 else ""
        lines.append(
            f"| {p.get('排名', '')} | {p['代码']} | {p.get('名称', '')} | {p['股数']} | "
            f"{float(p['成本价']):.2f} | {float(p['标记价']):.2f} | "
            f"{float(p['市值美元']):,.2f} | {s}{pp:,.2f} | {s}{pc:.2f}% |"
        )
    lines.append("")
    hints = state.get("_本次调仓提示") or []
    hist = state.get("调仓提示") or []
    show = hints or (hist[-3:] if hist else [])
    if show:
        lines.append("## 调仓提示（未自动换仓）")
        lines.append("")
        for h in show:
            lines.append(f"- {h}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*纸面模拟，非真实经纪商成交。成员变动仅记录提示，不会自动买卖。*")
    lines.append("")
    return "\n".join(lines)


def report(
    state_path: Path = DEFAULT_STATE,
    report_path: Path = DEFAULT_REPORT,
    top5_path: Path = DEFAULT_TOP5,
    refresh: bool = False,
) -> str:
    if refresh or not state_path.exists():
        update(top5_path, state_path)
    state = _load_json(state_path)
    text = format_report(state)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    return text


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TOP5 纸面组合盈亏")
    p.add_argument(
        "command",
        choices=["update", "report", "init"],
        help="update=刷新标记价；report=中文摘要；init=强制重建账本",
    )
    p.add_argument("--top5", default=str(DEFAULT_TOP5), help="top5.json 路径")
    p.add_argument("--state", default=str(DEFAULT_STATE), help="portfolio_top5.json 路径")
    p.add_argument("--out", default=str(DEFAULT_REPORT), help="报告 markdown 路径")
    args = p.parse_args(argv)

    top5_path = Path(args.top5)
    state_path = Path(args.state)
    report_path = Path(args.out)

    if args.command == "init":
        init_state(top5_path, state_path, force=True)
        state = update(top5_path, state_path)
        text = format_report(state)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text, encoding="utf-8")
        print(text)
        print(
            json.dumps(
                {"状态": "已初始化", "路径": str(state_path), "报告": str(report_path)},
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "update":
        state = update(top5_path, state_path)
        text = format_report(state)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text, encoding="utf-8")
        print(text)
        return 0
    if args.command == "report":
        text = report(state_path, report_path, top5_path, refresh=False)
        print(text)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
