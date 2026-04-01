"""Consensus Agent — 애널리스트 컨센서스 에이전트.

Fetch: yfinance → 투자의견(strongBuy/buy/hold/sell), 목표가(high/low/mean/median)
Analyze: LLM이 컨센서스 종합 판단
Score: Rule-based (의견비율 40%, 목표가 괴리율 35%, 의견 변화 추세 25%)
"""

import json

from agents.base import BaseAgent
from tools.cache import cached_api_call


def _fetch_consensus(ticker: str) -> dict | None:
    """yfinance로 애널리스트 컨센서스 데이터 가져오기."""
    import yfinance as yf

    try:
        stock = yf.Ticker(ticker)

        # recommendations
        recs = stock.recommendations
        if recs is not None and not recs.empty:
            current = recs.iloc[0]
            strong_buy = int(current.get("strongBuy", 0))
            buy = int(current.get("buy", 0))
            hold = int(current.get("hold", 0))
            sell = int(current.get("sell", 0))
            strong_sell = int(current.get("strongSell", 0))

            # 이전 달과 비교 (추세)
            if len(recs) >= 2:
                prev = recs.iloc[1]
                prev_bullish = int(prev.get("strongBuy", 0)) + int(prev.get("buy", 0))
                curr_bullish = strong_buy + buy
                trend = "improving" if curr_bullish > prev_bullish else "declining" if curr_bullish < prev_bullish else "stable"
            else:
                trend = "stable"
        else:
            strong_buy, buy, hold, sell, strong_sell = 0, 0, 0, 0, 0
            trend = "unknown"

        # price targets
        targets = stock.analyst_price_targets
        if targets:
            current_price = float(targets.get("current", 0))
            target_mean = float(targets.get("mean", 0))
            target_high = float(targets.get("high", 0))
            target_low = float(targets.get("low", 0))
            target_median = float(targets.get("median", 0))
        else:
            current_price, target_mean, target_high, target_low, target_median = 0, 0, 0, 0, 0

        # 목표가 괴리율
        if current_price > 0 and target_mean > 0:
            upside_pct = ((target_mean - current_price) / current_price) * 100
        else:
            upside_pct = 0.0

        total_opinions = strong_buy + buy + hold + sell + strong_sell

        return {
            "ticker": ticker,
            "strong_buy": strong_buy,
            "buy": buy,
            "hold": hold,
            "sell": sell,
            "strong_sell": strong_sell,
            "total_opinions": total_opinions,
            "trend": trend,
            "current_price": round(current_price, 2),
            "target_mean": round(target_mean, 2),
            "target_median": round(target_median, 2),
            "target_high": round(target_high, 2),
            "target_low": round(target_low, 2),
            "upside_pct": round(upside_pct, 2),
        }
    except Exception:
        return None


def _score_opinion_ratio(data: dict) -> float:
    """투자의견 비율 스코어. 매수 비율 높을수록 좋음."""
    total = data.get("total_opinions", 0)
    if total == 0:
        return 0.50

    bullish = data.get("strong_buy", 0) + data.get("buy", 0)
    bearish = data.get("sell", 0) + data.get("strong_sell", 0)
    bullish_ratio = bullish / total

    if bullish_ratio >= 0.8:
        return 0.90
    elif bullish_ratio >= 0.6:
        return 0.75
    elif bullish_ratio >= 0.4:
        return 0.55
    elif bullish_ratio >= 0.2:
        return 0.35
    else:
        return 0.15


def _score_upside(upside_pct: float) -> float:
    """목표가 괴리율 스코어. 상승 여력 클수록 좋음."""
    if upside_pct >= 30:
        return 0.90
    elif upside_pct >= 20:
        return 0.80
    elif upside_pct >= 10:
        return 0.65
    elif upside_pct >= 0:
        return 0.50
    elif upside_pct >= -10:
        return 0.35
    else:
        return 0.15


def _score_trend(trend: str) -> float:
    """의견 변화 추세 스코어."""
    if trend == "improving":
        return 0.80
    elif trend == "stable":
        return 0.50
    elif trend == "declining":
        return 0.25
    else:
        return 0.50


class ConsensusAgent(BaseAgent):
    agent_key = "consensus"

    def fetch(self, state: dict) -> dict | None:
        ticker = state["ticker"]
        return cached_api_call(
            key=f"consensus:{ticker}",
            fetcher=lambda: _fetch_consensus(ticker),
            ttl_hours=24,
        )

    def get_system_prompt(self) -> str:
        return """You are an analyst consensus expert. Given analyst recommendations and price targets, assess:
1. consensus_view: "strong_buy" | "buy" | "hold" | "sell" based on the distribution
2. target_assessment: "significant_upside" | "moderate_upside" | "fairly_valued" | "overvalued"
3. confidence_in_consensus: "high" (many analysts agree) | "medium" | "low" (few analysts or divided)
4. key_insight: one notable observation (Korean)
5. summary_kr: Korean summary, 2-3 sentences

RESPOND IN JSON ONLY."""

    def get_analysis_prompt(self, raw_data: dict, state: dict) -> str:
        return json.dumps({
            "ticker": state["ticker"],
            "strong_buy": raw_data.get("strong_buy"),
            "buy": raw_data.get("buy"),
            "hold": raw_data.get("hold"),
            "sell": raw_data.get("sell"),
            "strong_sell": raw_data.get("strong_sell"),
            "total_opinions": raw_data.get("total_opinions"),
            "trend": raw_data.get("trend"),
            "current_price": raw_data.get("current_price"),
            "target_mean": raw_data.get("target_mean"),
            "target_median": raw_data.get("target_median"),
            "upside_pct": raw_data.get("upside_pct"),
        }, ensure_ascii=False)

    def calculate_score(self, raw_data: dict, analysis: dict) -> float:
        """Rule-based: 의견비율(40%) + 목표가 괴리율(35%) + 의견 추세(25%)."""
        opinion_score = _score_opinion_ratio(raw_data)
        upside_score = _score_upside(raw_data.get("upside_pct", 0))
        trend_score = _score_trend(raw_data.get("trend", "stable"))

        return opinion_score * 0.40 + upside_score * 0.35 + trend_score * 0.25
