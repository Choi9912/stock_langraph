"""Synthesizer — 7개 에이전트 스코어를 종합하여 시그널 생성.

기간별 가중치 테이블 적용 → 종합 스코어 → 시그널 + confidence.
"""

from utils.score_calculator import calculate_weighted_score, score_to_signal

REQUIRED_AGENTS = ["price", "fundamental", "disclosure", "news", "macro", "supply_demand", "consensus"]


def synthesize(state: dict) -> dict:
    """에이전트 결과 종합 → signal, confidence, reasoning."""
    agent_results = state.get("agent_results", {})
    period = state.get("analysis_period", "short")

    # 각 에이전트 스코어 추출
    scores = {}
    score_details = []
    for key in REQUIRED_AGENTS:
        result = agent_results.get(key, {})
        score = result.get("score", 0.0)
        scores[key] = score
        score_details.append(f"{key}={score:.2f}")

    # 가중치 적용 종합 스코어 (종목별 가중치 우선)
    ticker = state.get("ticker", "")
    weighted_score = calculate_weighted_score(scores, period, ticker)
    signal = score_to_signal(weighted_score)

    # confidence: 에이전트 일관성 기반
    # 모든 에이전트가 같은 방향이면 높은 confidence
    valid_scores = [s for s in scores.values() if s > 0]
    if valid_scores:
        mean = sum(valid_scores) / len(valid_scores)
        variance = sum((s - mean) ** 2 for s in valid_scores) / len(valid_scores)
        # 분산이 낮을수록 confidence 높음 (max variance ~0.25)
        consistency = max(0.0, 1.0 - (variance / 0.25) * 2)
        # 유효 에이전트 비율 반영
        coverage = len(valid_scores) / len(REQUIRED_AGENTS)
        confidence = round(consistency * 0.6 + coverage * 0.4, 3)
    else:
        confidence = 0.0

    # reasoning 생성
    reasoning_parts = [
        f"종합 스코어: {weighted_score:.3f} ({period} 기간 가중치 적용)",
        f"개별 스코어: {', '.join(score_details)}",
        f"시그널: {signal} (confidence: {confidence:.1%})",
    ]

    # 주요 요인 분석
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top = sorted_scores[0]
    bottom = sorted_scores[-1]
    reasoning_parts.append(f"가장 긍정적: {top[0]} ({top[1]:.2f})")
    reasoning_parts.append(f"가장 부정적: {bottom[0]} ({bottom[1]:.2f})")

    # risk factors
    risk_factors = []
    if scores.get("price", 0.5) < 0.3:
        risk_factors.append("기술적 지표 약세 (과매수 또는 하락 추세)")
    if scores.get("fundamental", 0.5) < 0.3:
        risk_factors.append("펀더멘털 부진 (고평가 또는 수익성 악화)")
    if scores.get("macro", 0.5) < 0.3:
        risk_factors.append("거시경제 리스크 (VIX 상승, 금리 인상)")
    if scores.get("news", 0.5) < 0.3:
        risk_factors.append("부정적 뉴스 심리")
    if scores.get("supply_demand", 0.5) < 0.3:
        risk_factors.append("수급 악화 (기관/외국인 매도세)")
    if scores.get("consensus", 0.5) < 0.3:
        risk_factors.append("애널리스트 부정적 의견 (목표가 하회)")

    failed = state.get("validation_result", {}).get("failed_agents", [])
    if failed:
        risk_factors.append(f"데이터 불완전: {', '.join(failed)} 에이전트 실패")

    return {
        "signal": signal,
        "confidence": confidence,
        "reasoning": "\n".join(reasoning_parts),
        "risk_factors": risk_factors,
    }
