"""Validator — 에이전트 결과 검증 + 재시도 대상 판별.

검증 항목:
1. 7개 에이전트 키 모두 존재하는지
2. 각 에이전트 score가 0.0이 아닌지 (error 없는지)
3. retry_count < 2인 경우에만 재시도 허용
"""

REQUIRED_AGENTS = ["price", "fundamental", "disclosure", "news", "macro", "supply_demand", "consensus"]
MAX_RETRY = 2


def validate(state: dict) -> dict:
    """에이전트 결과를 검증하고 retry_targets를 설정."""
    agent_results = state.get("agent_results", {})
    retry_count = state.get("retry_count", 0)

    failed = []
    details = {}

    for agent_key in REQUIRED_AGENTS:
        if agent_key not in agent_results:
            failed.append(agent_key)
            details[agent_key] = "missing"
        elif "error" in agent_results[agent_key]:
            failed.append(agent_key)
            details[agent_key] = agent_results[agent_key]["error"]
        elif agent_results[agent_key].get("score", 0.0) == 0.0:
            # score 0.0이면서 error가 없으면 데이터 부족일 수 있음
            failed.append(agent_key)
            details[agent_key] = "score is 0.0 (possible data issue)"

    # 재시도 가능 여부 판단
    if failed and retry_count < MAX_RETRY:
        return {
            "validation_result": {
                "passed": False,
                "failed_agents": failed,
                "details": details,
            },
            "retry_targets": failed,
            "retry_count": retry_count + 1,
        }

    # 재시도 불가 또는 모두 통과
    return {
        "validation_result": {
            "passed": len(failed) == 0,
            "failed_agents": failed,
            "details": details,
            "note": "max retry reached" if failed else "all passed",
        },
        "retry_targets": [],
    }
