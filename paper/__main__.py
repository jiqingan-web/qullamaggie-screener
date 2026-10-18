"""命令行：python -m paper run | status | reset"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from paper.broker import DEFAULT_SCAN, STATE_PATH, default_state, run_once, save_state, status


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="库拉马吉风格纸面交易")
    p.add_argument("command", choices=["run", "status", "reset"], help="run=按信号模拟一步；status=查看；reset=重置")
    p.add_argument("--scan", default=str(DEFAULT_SCAN), help="last_scan.json 路径")
    p.add_argument("--state", default=str(STATE_PATH), help="状态 JSON 路径")
    args = p.parse_args(argv)

    scan = Path(args.scan)
    state_path = Path(args.state)

    if args.command == "reset":
        save_state(default_state(), state_path)
        print(json.dumps({"状态": "已重置", "路径": str(state_path)}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "status":
        print(json.dumps(status(state_path), ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        if not scan.exists():
            print(json.dumps({"错误": f"找不到信号文件：{scan}", "提示": "请先运行筛选或使用仓库 data/last_scan.json"}, ensure_ascii=False))
            return 1
        out = run_once(scan, state_path)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
