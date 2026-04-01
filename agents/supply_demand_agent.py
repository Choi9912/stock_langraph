"""Supply/Demand Agent — 수급 분석 에이전트.

Fetch: yfinance → 기관 보유 비율, 주요 기관 보유 변동, 내부자 보유율
Analyze: LLM이 수급 동향 종합 판단
Score: Rule-based (기관보유비율 30%, 기관보유변동 35%, 내부자보유율 20%, 기관수 15%)
"""

import json

from agents.base import BaseAgent
from tools.cache import cached_api_call


def _fetch_supply_demand(ticker: str) -> dict | None:
    """yfinance로 수급 데이터 가져오기."""
    import yfinance as yf

    try:
        stock = yf.Ticker(ticker)

        # major_holders: 내부자/기관 보유 비율
        mh = stock.major_holders
        if mh is not None and not mh.empty:
            # index가 Breakdown 키 (insidersPercentHeld 등)
            insiders_pct = float(mh.loc["insidersPercentHeld", "Value"]) if "insidersPercentHeld" in mh.index else 0.0
            institutions_pct = float(mh.loc["institutionsPercentHeld", "Value"]) if "institutionsPercentHeld" in mh.index else 0.0
            institutions_count = int(mh.loc["institutionsCount", "Value"]) if "institutionsCount" in mh.index else 0
        else:
            insiders_pct = 0.0
            institutions_pct = 0.0
            institutions_count = 0

        # institutional_holders: 상위 기관 보유 변동
        ih = stock.institutional_holders
        avg_pct_change = 0.0
        top_holders = []
        if ih is not None and not ih.empty:
            changes = ih["pctChange"].dropna()
            if len(changes) > 0:
                avg_pct_change = float(changes.mean())
            for _, row in ih.head(5).iterrows():
                top_holders.append({
                    "holder": str(row.get("Holder", "")),
                    "pct_change": float(row.get("pctChange", 0)),
                })

        return {
            "ticker": ticker,
            "insiders_pct": round(insiders_pct * 100, 2),
            "institutions_pct": round(institutions_pct * 100, 2),
            "institutions_count": institutions_count,
            "avg_institution_pct_change": round(avg_pct_change * 100, 2),
            "top_holders": top_holders,
        }
    except Exception:
        return None


def _score_institutions_pct(pct: float) -> float:
    """기관 보유 비율 스코어. 높을수록 신뢰성."""
    if pct >= 60:
        return 0.85
    elif pct >= 40:
        return 0.70
    elif pct >= 20:
        return 0.55
    elif pct >= 10:
        return 0.40
    else:
        return 0.25


def _score_institution_change(avg_change: float) -> float:
    """기관 보유 변동 스코어. 순매수(양수)면 호재."""
    if avg_change > 3:
        return 0.90
    elif avg_change > 1:
        return 0.75
    elif avg_change > 0:
        return 0.60
    elif avg_change > -1:
        return 0.45
    elif avg_change > -3:
        return 0.30
    else:
        return 0.15


def _score_insiders_pct(pct: float) -> float:
    """내부자 보유율 스코어. 적당히 높으면 경영진 신뢰."""
    if 5 <= pct <= 30:
        return 0.80
    elif pct > 30:
        return 0.60  # 너무 높으면 유동성 우려
    elif pct >= 1:
        return 0.50
    else:
        return 0.35


def _score_institutions_count(count: int) -> float:
    """기관 수 스코어. 많을수록 관심도 높음."""
    if count >= 500:
        return 0.85
    elif count >= 200:
        return 0.70
    elif count >= 50:
        return 0.55
    elif count >= 10:
        return 0.40
    else:
        return 0.25


class SupplyDemandAgent(BaseAgent):
    agent_key = "supply_demand"

    def fetch(self, state: dict) -> dict | None:
        ticker = state["ticker"]
        return cached_api_call(
            key=f"supply_demand:{ticker}",
            fetcher=lambda: _fetch_supply_demand(ticker),
            ttl_hours=12,
        )

    def get_system_prompt(self) -> str:
        return """You are a supply/demand (investor flow) analyst. Given institutional holding data, assess:
1. flow_trend: "accumulating" | "distributing" | "neutral"
2. institutional_confidence: "high" | "medium" | "low"
3. key_observation: one notable finding about the holding pattern (Korean)
4. summary_kr: Korean summary, 2-3 sentences about supply/demand dynamics

RESPOND IN JSON ONLY."""

    def get_analysis_prompt(self, raw_data: dict, state: dict) -> str:
        return json.dumps({
            "ticker": state["ticker"],
            "insiders_pct": raw_data.get("insiders_pct"),
            "institutions_pct": raw_data.get("institutions_pct"),
            "institutions_count": raw_data.get("institutions_count"),
            "avg_institution_pct_change": raw_data.get("avg_institution_pct_change"),
            "top_holders": raw_data.get("top_holders", []),
        }, ensure_ascii=False)

    def calculate_score(self, raw_data: dict, analysis: dict) -> float:
        """Rule-based: 기관보유비율(30%) + 기관변동(35%) + 내부자(20%) + 기관수(15%)."""
        inst_pct_score = _score_institutions_pct(raw_data.get("institutions_pct", 0))
        change_score = _score_institution_change(raw_data.get("avg_institution_pct_change", 0))
        insider_score = _score_insiders_pct(raw_data.get("insiders_pct", 0))
        count_score = _score_institutions_count(raw_data.get("institutions_count", 0))

        return inst_pct_score * 0.30 + change_score * 0.35 + insider_score * 0.20 + count_score * 0.15
