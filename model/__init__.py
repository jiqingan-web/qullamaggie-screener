"""爆涨潜力评分模型（库拉马吉风格）。"""

from .scoring import WEIGHTS, POSITION, run_top5, score_burst

__all__ = ["WEIGHTS", "POSITION", "run_top5", "score_burst"]
