"""Stock Advisor 진입점."""

import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from graph.graph import app


def run(user_input: str) -> None:
    initial_state = {
        "raw_input": user_input,
        "ticker": "",
        "market": "KRX",
        "analysis_period": "short",
        "agent_results": {},
        "validation_result": {},
        "retry_targets": [],
        "retry_count": 0,
        "signal": "HOLD",
        "confidence": 0.0,
        "reasoning": "",
        "risk_factors": [],
        "final_report": "",
        "messages": [],
        "error_log": [],
    }

    result = app.invoke(initial_state)

    # 최종 리포트 출력
    report = result.get("final_report", "")
    if report:
        print(report)
    else:
        print("[!] 리포트 생성 실패")
        print(f"Signal: {result.get('signal', 'N/A')}")
        print(f"Errors: {result.get('error_log', [])}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
    else:
        user_input = input("분석할 종목을 입력하세요: ")
    run(user_input)
