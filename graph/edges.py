"""Conditional edge 함수들.

route_after_validation: retry_targets가 있으면 retry, 없으면 synthesizer
route_fan_out: 재시도 대상 에이전트만 선택적 실행
"""

from typing import Literal

AGENT_NODES = ["price_agent", "fundamental_agent", "disclosure_agent", "news_agent", "macro_agent"]
AGENT_KEY_TO_NODE = {
    "price": "price_agent",
    "fundamental": "fundamental_agent",
    "disclosure": "disclosure_agent",
    "news": "news_agent",
    "macro": "macro_agent",
}


def route_after_validation(state: dict) -> Literal["retry_fan_out", "synthesizer"]:
    """Validator 결과에 따라 재시도 또는 합성으로 분기."""
    retry_targets = state.get("retry_targets", [])
    if retry_targets:
        return "retry_fan_out"
    return "synthesizer"


def get_retry_targets(state: dict) -> list[str]:
    """재시도 대상 에이전트 노드 이름 목록 반환."""
    retry_targets = state.get("retry_targets", [])
    return [AGENT_KEY_TO_NODE[k] for k in retry_targets if k in AGENT_KEY_TO_NODE]
