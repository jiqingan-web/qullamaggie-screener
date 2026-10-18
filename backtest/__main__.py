"""命令行：python -m backtest [--full] [--start YYYY-MM-DD] [--end YYYY-MM-DD]"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# 仓库根加入 path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.config import DEFAULT_END, DEFAULT_START, OUTPUT_DIR, USE_MARKET_FILTER
from backtest.data import download_many, load_market, resolve_tickers
from backtest.engine import run_backtest
from backtest.metrics import save_equity_curve, save_stats_json, save_trades_csv
from backtest.signals import build_panels


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="库拉马吉风格动量突破回测")
    p.add_argument("--full", action="store_true", help="使用完整 universe（较慢）")
    p.add_argument("--start", default=DEFAULT_START, help="起始日")
    p.add_argument("--end", default=DEFAULT_END, help="结束日")
    p.add_argument("--no-market-filter", action="store_true", help="关闭纳指过滤")
    p.add_argument("--force-download", action="store_true", help="强制重新下载行情")
    p.add_argument("--out", default=str(OUTPUT_DIR), help="输出目录")
    args = p.parse_args(argv)

    tickers = resolve_tickers(full=args.full)
    print(f"股票池数量：{len(tickers)}（{'全池' if args.full else '样例子集'}）")
    print(f"区间：{args.start} → {args.end}")
    t0 = time.time()
    prices = download_many(tickers, args.start, args.end, force=args.force_download)
    print(f"已下载/缓存有效标的：{len(prices)}，用时 {time.time()-t0:.1f}s")
    market = load_market(args.start, args.end, force=args.force_download)
    panels = build_panels(prices)
    print(f"指标就绪标的：{len(panels)}")

    result = run_backtest(
        panels,
        market,
        start=args.start,
        end=args.end,
        use_market_filter=not args.no_market_filter and USE_MARKET_FILTER,
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # 临时改写 OUTPUT 路径：直接传 path
    png = save_equity_curve(result, out / "equity_curve.png")
    extra = {
        "股票池模式": "全池" if args.full else "样例子集",
        "标的数_请求": len(tickers),
        "标的数_有效": len(panels),
        "起始": args.start,
        "结束": args.end,
        "市场过滤": not args.no_market_filter,
        "样例限制说明": (
            "默认使用约 50 只高流动性动量名子集以加快演示；"
            "日线近似开盘区间突破；免费 yfinance 数据可能缺数；"
            "非实盘、无滑点冲击完整建模。加 --full 可扫完整 universe。"
        ),
    }
    js = save_stats_json(result, out / "stats.json", extra=extra)
    csv_path = save_trades_csv(result, out / "trades.csv")

    # 同步一份到 Pages 可托管路径
    pages_data = ROOT / "data"
    pages_data.mkdir(parents=True, exist_ok=True)
    try:
        import shutil

        shutil.copy2(png, pages_data / "equity_curve.png")
        shutil.copy2(js, pages_data / "backtest_stats.json")
    except Exception as e:
        print(f"复制到 data/ 失败：{e}")

    print("--- 回测统计 ---")
    print(json.dumps(result.stats, ensure_ascii=False, indent=2))
    print(f"权益曲线：{png}")
    print(f"统计 JSON：{js}")
    print(f"成交明细：{csv_path}")
    print(f"总用时：{time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
