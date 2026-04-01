import json
import re
import traceback
from abc import ABC, abstractmethod
from typing import Any

from langchain_openai import ChatOpenAI

from config.settings import LLM_MODEL, OPENAI_API_KEY


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(model=LLM_MODEL, api_key=OPENAI_API_KEY, temperature=0)


def parse_json_response(text: str) -> dict:
    """LLM 응답에서 JSON 추출. ```json 펜스 제거 포함."""
    cleaned = re.sub(r"```json\s*", "", text)
    cleaned = re.sub(r"```\s*$", "", cleaned)
    cleaned = cleaned.strip()
    return json.loads(cleaned)


class BaseAgent(ABC):
    agent_key: str  # "price", "fundamental", "disclosure", "news", "macro"

    @abstractmethod
    def fetch(self, state: dict) -> dict:
        """API 호출만. LLM 사용 금지."""
        ...

    @abstractmethod
    def get_system_prompt(self) -> str:
        """에이전트별 시스템 프롬프트."""
        ...

    @abstractmethod
    def get_analysis_prompt(self, raw_data: dict, state: dict) -> str:
        """Analyze 단계에서 LLM에 보낼 프롬프트."""
        ...

    @abstractmethod
    def calculate_score(self, raw_data: dict, analysis: dict) -> float:
        """Rule-based 또는 LLM-scored. 0.0~1.0 반환."""
        ...

    def analyze(self, raw_data: dict, state: dict) -> dict:
        """LLM 호출 → JSON 파싱."""
        llm = _get_llm()
        system_prompt = self.get_system_prompt()
        analysis_prompt = self.get_analysis_prompt(raw_data, state)

        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": analysis_prompt},
        ])
        return parse_json_response(response.content)

    @staticmethod
    def validate_score(score: Any) -> float:
        """0.0~1.0 범위 강제."""
        try:
            s = float(score)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, s))

    def run(self, state: dict) -> dict:
        """Fetch → Analyze → Score. 예외 시 error_log 기록 + score 0.0."""
        try:
            raw_data = self.fetch(state)
            if raw_data is None:
                return {
                    "agent_results": {
                        self.agent_key: {"score": 0.0, "error": "fetch returned None"}
                    },
                    "error_log": [f"{self.agent_key}: fetch returned None"],
                }

            analysis = self.analyze(raw_data, state)
            score = self.validate_score(self.calculate_score(raw_data, analysis))

            return {
                "agent_results": {
                    self.agent_key: {
                        "raw_data": raw_data,
                        "analysis": analysis,
                        "score": score,
                    }
                },
            }
        except Exception as e:
            error_msg = f"{self.agent_key}: {type(e).__name__}: {e}"
            traceback.print_exc()
            return {
                "agent_results": {
                    self.agent_key: {"score": 0.0, "error": error_msg}
                },
                "error_log": [error_msg],
            }


def make_node(agent: BaseAgent):
    """LangGraph 노드로 변환."""
    def node_fn(state: dict) -> dict:
        return agent.run(state)
    node_fn.__name__ = f"{agent.agent_key}_agent_node"
    return node_fn
