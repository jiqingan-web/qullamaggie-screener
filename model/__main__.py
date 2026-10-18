"""CLI: python -m model top5"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def cmd_top5(args: argparse.Namespace) -> int:
    from model.scoring import run_top5

    t0 = time.time()
    print("开始爆涨潜力扫描（TOP5）…", flush=True)

    def prog(done, total):
        print(f"  进度 {done}/{total}", flush=True)

    res = run_top5(progress_cb=prog)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    elapsed = time.time() - t0
    n = res.get("统计", {}).get("入选", 0)
    print(f"完成，用时 {elapsed:.1f}s，写入 {out}，TOP {n}", flush=True)
    for r in res.get("结果", []):
        print(
            f"  #{r.get('排名')} {r['代码']:6s} {str(r.get('名称',''))[:20]:20s} "
            f"爆涨分={r.get('爆涨分')} 建议股数={r.get('建议仓位股数')} "
            f"市值≈{r.get('建议市值美元')} ({r.get('建议仓位占比%')}%)",
            flush=True,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="爆涨潜力评分模型")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("top5", help="扫描并写出 data/top5.json")
    t.add_argument(
        "--out",
        default=str(ROOT / "data" / "top5.json"),
        help="输出 JSON 路径",
    )
    t.set_defaults(func=cmd_top5)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
