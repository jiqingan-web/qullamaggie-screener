"""统计输出与权益曲线图（中文标签）。"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from .config import OUTPUT_DIR
from .engine import BacktestResult, trades_to_records


def _setup_chinese_font() -> str:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]
    for p in candidates:
        if Path(p).exists():
            font_manager.fontManager.addfont(p)
            prop = font_manager.FontProperties(fname=p)
            name = prop.get_name()
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            return name
    plt.rcParams["axes.unicode_minus"] = False
    return "DejaVu Sans"


def save_equity_curve(result: BacktestResult, path: Path | None = None) -> Path:
    _setup_chinese_font()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = path or (OUTPUT_DIR / "equity_curve.png")
    eq = result.equity
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    axes[0].plot(eq.index, eq.values, color="#1f77b4", lw=1.4, label="账户权益")
    axes[0].set_ylabel("权益（美元）")
    axes[0].set_title("库拉马吉风格动量突破 — 回测权益曲线")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="upper left")
    dd = eq / eq.cummax() - 1.0
    axes[1].fill_between(dd.index, dd.values * 100, 0, color="#d62728", alpha=0.45, label="回撤")
    axes[1].set_ylabel("回撤（%）")
    axes[1].set_xlabel("日期")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="lower left")
    # 注释关键指标
    s = result.stats
    note = (
        f"年化 {s.get('年化收益CAGR%', '—')}%  |  "
        f"最大回撤 {s.get('最大回撤%', '—')}%  |  "
        f"胜率 {s.get('胜率%', '—')}%  |  "
        f"利润因子 {s.get('盈亏比_利润因子', '—')}  |  "
        f"买入 {s.get('买入笔数', 0)} 笔"
    )
    fig.text(0.5, 0.01, note, ha="center", fontsize=9, color="#333")
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def save_stats_json(result: BacktestResult, path: Path | None = None, extra: dict | None = None) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = path or (OUTPUT_DIR / "stats.json")
    payload = {
        "统计": result.stats,
        "说明": {
            "策略": "库拉马吉风格动量突破（日线近似）",
            "数据源": "yfinance",
            "免责": "仅供学习研究，不构成投资建议",
        },
        "成交明细笔数": len(result.trades),
        "成交明细样例": trades_to_records(result.trades)[:30],
    }
    if extra:
        payload["运行参数"] = extra
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_trades_csv(result: BacktestResult, path: Path | None = None) -> Path:
    import pandas as pd

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = path or (OUTPUT_DIR / "trades.csv")
    pd.DataFrame(trades_to_records(result.trades)).to_csv(path, index=False, encoding="utf-8-sig")
    return path
