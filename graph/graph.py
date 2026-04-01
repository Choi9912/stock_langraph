"""LangGraph 그래프 빌드.

InputParser → [7 Agents 병렬] → Validator → (retry or Synthesizer) → Report → END

재시도 시: retry_fan_out → [실패 에이전트만 병렬] → Validator (최대 2회)
"""

from langgraph.graph import END, StateGraph

from agents.base import make_node
from agents.consensus_agent import ConsensusAgent
from agents.disclosure_agent import DisclosureAgent
from agents.fundamental_agent import FundamentalAgent
from agents.input_parser import parse_input
from agents.macro_agent import MacroAgent
from agents.news_agent import NewsAgent
from agents.price_agent import PriceAgent
from agents.report_generator import generate_report
from agents.supply_demand_agent import SupplyDemandAgent
from agents.synthesizer import synthesize
from agents.validator import validate
from graph.edges import route_after_validation
from graph.state import StockAnalysisState

# 에이전트 인스턴스
price_agent = PriceAgent()
fundamental_agent = FundamentalAgent()
disclosure_agent = DisclosureAgent()
news_agent = NewsAgent()
macro_agent = MacroAgent()
supply_demand_agent = SupplyDemandAgent()
consensus_agent = ConsensusAgent()

ALL_AGENT_NODES = [
    "price_agent", "fundamental_agent", "disclosure_agent",
    "news_agent", "macro_agent", "supply_demand_agent", "consensus_agent",
]

AGENT_KEY_TO_NODE = {
    "price": "price_agent",
    "fundamental": "fundamental_agent",
    "disclosure": "disclosure_agent",
    "news": "news_agent",
    "macro": "macro_agent",
    "supply_demand": "supply_demand_agent",
    "consensus": "consensus_agent",
}


def _route_retry_fan_out(state: dict) -> list[str]:
    """재시도 대상 에이전트 노드만 반환."""
    retry_targets = state.get("retry_targets", [])
    return [AGENT_KEY_TO_NODE[k] for k in retry_targets if k in AGENT_KEY_TO_NODE]


def build_graph() -> StateGraph:
    graph = StateGraph(StockAnalysisState)

    # ── 노드 등록 ──
    graph.add_node("input_parser", parse_input)
    graph.add_node("price_agent", make_node(price_agent))
    graph.add_node("fundamental_agent", make_node(fundamental_agent))
    graph.add_node("disclosure_agent", make_node(disclosure_agent))
    graph.add_node("news_agent", make_node(news_agent))
    graph.add_node("macro_agent", make_node(macro_agent))
    graph.add_node("supply_demand_agent", make_node(supply_demand_agent))
    graph.add_node("consensus_agent", make_node(consensus_agent))
    graph.add_node("validator", validate)
    graph.add_node("synthesizer", synthesize)
    graph.add_node("report_generator", generate_report)

    # ── 엣지 연결 ──

    # 1. 진입 → InputParser
    graph.set_entry_point("input_parser")

    # 2. InputParser → 7개 에이전트 병렬 (fan-out)
    graph.add_conditional_edges(
        "input_parser",
        lambda state: ALL_AGENT_NODES,
        {node: node for node in ALL_AGENT_NODES},
    )

    # 3. 7개 에이전트 → Validator (fan-in)
    for node in ALL_AGENT_NODES:
        graph.add_edge(node, "validator")

    # 4. Validator → retry 또는 synthesizer (conditional)
    graph.add_conditional_edges(
        "validator",
        route_after_validation,
        {
            "retry_fan_out": "retry_fan_out",
            "synthesizer": "synthesizer",
        },
    )

    # 5. retry_fan_out 노드: 실패한 에이전트만 다시 실행
    graph.add_node("retry_fan_out", lambda state: {})  # pass-through
    graph.add_conditional_edges(
        "retry_fan_out",
        _route_retry_fan_out,
        {node: node for node in ALL_AGENT_NODES},
    )

    # 6. Synthesizer → Report → END
    graph.add_edge("synthesizer", "report_generator")
    graph.add_edge("report_generator", END)

    return graph.compile()


app = build_graph()
