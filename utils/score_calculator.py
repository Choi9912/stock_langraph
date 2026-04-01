"""기간별 + 종목별 가중치 적용 스코어 계산."""

import json
from pathlib import Path

from config.settings import SIGNAL_THRESHOLDS, WEIGHT_TABLE

# 종목별 가중치 파일 (백테스트 결과에서 생성)
STOCK_WEIGHTS_PATH = Path("data/backtest/stock_weights.json")

# 종목별 가중치 캐시
_stock_weights: dict | None = None


def _load_stock_weights() -> dict:
    """종목별 가중치 로드."""
    global _stock_weights
    if _stock_weights is not None:
        return _stock_weights

    if STOCK_WEIGHTS_PATH.exists():
        with open(STOCK_WEIGHTS_PATH, "r", encoding="utf-8") as f:
            _stock_weights = json.load(f)
    else:
        _stock_weights = {}

    return _stock_weights


def calculate_weighted_score(
    agent_scores: dict[str, float],
    period: str,
    ticker: str = "",
) -> float:
    """에이전트 스코어에 가중치를 적용한 종합 스코어.

    1차: 종목별 가중치 (있으면)
    2차: 기간별 기본 가중치
    """
    # 종목별 가중치 확인
    stock_weights = _load_stock_weights()
    if ticker and ticker in stock_weights:
        weights = stock_weights[ticker].get("weights", {})
    else:
        weights = WEIGHT_TABLE.get(period, WEIGHT_TABLE["short"])

    total = 0.0
    for agent_key, weight in weights.items():
        score = agent_scores.get(agent_key, 0.0)
        total += score * weight
    return round(total, 4)


def score_to_signal(score: float) -> str:
    """스코어 → 시그널 변환."""
    if score >= SIGNAL_THRESHOLDS["STRONG_BUY"]:
        return "STRONG_BUY"
    elif score >= SIGNAL_THRESHOLDS["BUY"]:
        return "BUY"
    elif score >= SIGNAL_THRESHOLDS["HOLD"]:
        return "HOLD"
    elif score >= SIGNAL_THRESHOLDS["SELL"]:
        return "SELL"
    else:
        return "STRONG_SELL"
