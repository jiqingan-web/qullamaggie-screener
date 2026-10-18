"""回测与纸面交易共用参数（对齐筛选器文档规则）。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
CACHE_DIR = Path(__file__).resolve().parent / "cache"

ACCOUNT_USD = 100_000.0
MIN_DOLLAR_VOLUME = 10_000_000.0  # 日成交额 ≥ 1000 万美元
RISK_PCT = 0.005  # 单笔风险 0.5%
MAX_OVERNIGHT_PCT = 0.30  # 单标的隔夜上限 30%
TYPICAL_SIZE_LOW = 0.10
TYPICAL_SIZE_HIGH = 0.15

# 相对强度：池内前约 1–2%
RS_TOP_PCT = 2.0
RS_REBALANCE_DAYS = 5  # 每周再平衡候选

# 突破 / 盘整近似（日线）
BREAKOUT_LOOKBACK = 20  # 突破近 N 日高点
CONSOL_LOOKBACK = 25
CONSOL_RANGE_PCT_MAX = 22.0  # 盘整相对振幅上限 %
MA_NEAR_PCT = 8.0  # 贴近 10 日均线
PRIOR_MOVE_LOOKBACK = 90
PRIOR_MOVE_MIN_PCT = 30.0

# 出场
PARTIAL_EXIT_DAYS = 4  # 3–5 日中取 4
PARTIAL_EXIT_FRAC = 1.0 / 3.0  # 先卖 1/3
TRAIL_MA = 10

# 市场过滤
MARKET_TICKER = "QQQ"
USE_MARKET_FILTER = True

# 样例回测（加速）：高流动性动量名子集；全池用 --full
SAMPLE_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMD", "AVGO", "META", "GOOGL", "AMZN", "TSLA", "NFLX",
    "CRM", "ORCL", "ADBE", "QCOM", "AMAT", "LRCX", "KLAC", "MU", "PLTR", "CRWD",
    "PANW", "SNOW", "NET", "SHOP", "UBER", "COIN", "MSTR", "SMCI", "ARM", "APP",
    "CELH", "CAVA", "DUOL", "AXON", "VRT", "VST", "CEG", "ANET", "DELL", "NOW",
    "TTD", "MELI", "BKNG", "COST", "LLY", "ISRG", "ENPH", "FSLR", "RKLB", "ASTS",
]

DEFAULT_START = "2020-01-01"
DEFAULT_END = "2025-12-31"
MAX_OPEN_POSITIONS = 8
COMMISSION_BPS = 1.0  # 单边万分之一近似
SLIPPAGE_BPS = 5.0
