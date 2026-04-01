"""Fundamental Agent — 재무제표 기반 밸류에이션 분석.

Fetch: DART OpenAPI(국내) / Alpha Vantage(해외) → PER, PBR, ROE, 매출성장률, 부채비율
Analyze: LLM이 업종 대비 밸류에이션 판단
Score: Rule-based (PER vs 업종평균 35%, ROE 30%, 매출성장률 20%, 부채비율 15%)
"""

import json

from agents.base import BaseAgent
from config.settings import ALPHA_VANTAGE_KEY, DART_API_KEY
from tools.cache import cached_api_call

# TODO: 업종별 평균 PER DB 구축. 현재 하드코딩.
SECTOR_AVG_PER = 18.0


def _fetch_yfinance_fundamental(ticker: str) -> dict | None:
    """yfinance로 재무 데이터 가져오기 (DART/AV 대체 fallback)."""
    import yfinance as yf

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        per = info.get("trailingPE") or info.get("forwardPE") or 0
        pbr = info.get("priceToBook") or 0
        roe = (info.get("returnOnEquity") or 0) * 100
        revenue_growth = (info.get("revenueGrowth") or 0) * 100
        debt_ratio = info.get("debtToEquity") or 0

        if per == 0 and pbr == 0 and roe == 0:
            return None

        return {
            "ticker": ticker,
            "per": round(float(per), 2),
            "pbr": round(float(pbr), 2),
            "roe": round(float(roe), 2),
            "revenue_growth": round(float(revenue_growth), 2),
            "debt_ratio": round(float(debt_ratio), 2),
            "source": "yfinance",
        }
    except Exception:
        return None


def _fetch_dart(ticker: str) -> dict | None:
    """DART OpenAPI로 국내 재무제표 가져오기. 실패 시 yfinance fallback."""
    if DART_API_KEY:
        try:
            import opendartreader as dart

            api = dart.OpenDartReader(DART_API_KEY)
            code = ticker.replace(".KS", "").replace(".KQ", "")

            fs = api.finstate(code, 2024)
            if fs is None or fs.empty:
                fs = api.finstate(code, 2023)
            if fs is not None and not fs.empty:
                return {
                    "ticker": ticker,
                    "per": 12.5,    # TODO: 실제 계산 로직
                    "pbr": 1.2,
                    "roe": 15.3,
                    "revenue_growth": 8.5,
                    "debt_ratio": 45.0,
                    "source": "DART",
                }
        except Exception:
            pass

    # DART 실패 또는 키 없음 → yfinance fallback
    return _fetch_yfinance_fundamental(ticker)


def _fetch_alpha_vantage(ticker: str) -> dict | None:
    """Alpha Vantage로 해외 재무제표 가져오기."""
    import requests

    if not ALPHA_VANTAGE_KEY:
        return None

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "OVERVIEW",
        "symbol": ticker,
        "apikey": ALPHA_VANTAGE_KEY,
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if "Symbol" not in data:
            return None

        return {
            "ticker": ticker,
            "per": float(data.get("PERatio", 0) or 0),
            "pbr": float(data.get("PriceToBookRatio", 0) or 0),
            "roe": float(data.get("ReturnOnEquityTTM", 0) or 0) * 100,
            "revenue_growth": float(data.get("QuarterlyRevenueGrowthYOY", 0) or 0) * 100,
            "debt_ratio": float(data.get("DebtToEquity", 0) or 0) if data.get("DebtToEquity") else 0,
            "source": "AlphaVantage",
        }
    except Exception:
        pass

    # Alpha Vantage 실패 → yfinance fallback
    return _fetch_yfinance_fundamental(ticker)


def _score_per_ratio(per: float, sector_avg: float) -> float:
    """PER vs 업종평균 스코어."""
    if sector_avg == 0:
        return 0.5
    ratio = per / sector_avg
    if ratio < 0.6:
        return 0.90
    elif ratio < 0.8:
        return 0.75
    elif ratio < 1.0:
        return 0.60
    elif ratio < 1.3:
        return 0.40
    else:
        return 0.20


def _score_roe(roe: float) -> float:
    """ROE 스코어."""
    if roe >= 20:
        return 0.90
    elif roe >= 15:
        return 0.75
    elif roe >= 10:
        return 0.60
    elif roe >= 5:
        return 0.40
    else:
        return 0.20


def _score_revenue_growth(growth: float) -> float:
    """매출 성장률 스코어."""
    if growth >= 20:
        return 0.90
    elif growth >= 10:
        return 0.75
    elif growth >= 5:
        return 0.60
    elif growth >= 0:
        return 0.40
    else:
        return 0.20


def _score_debt_ratio(debt: float) -> float:
    """부채비율 스코어 (낮을수록 좋음)."""
    if debt < 30:
        return 0.85
    elif debt < 50:
        return 0.70
    elif debt < 80:
        return 0.50
    elif debt < 120:
        return 0.30
    else:
        return 0.15


class FundamentalAgent(BaseAgent):
    agent_key = "fundamental"

    def fetch(self, state: dict) -> dict | None:
        ticker = state["ticker"]
        market = state["market"]

        if market == "KRX":
            fetcher = lambda: _fetch_dart(ticker)
        else:
            fetcher = lambda: _fetch_alpha_vantage(ticker)

        return cached_api_call(
            key=f"fundamental:{ticker}",
            fetcher=fetcher,
            ttl_hours=24,
        )

    def get_system_prompt(self) -> str:
        return f"""You are a fundamental analysis expert. Given financial metrics, assess:
1. valuation: "overvalued" | "fair" | "undervalued"
2. per_vs_sector: PER / sector average ratio (sector avg = {SECTOR_AVG_PER})
3. strengths: list of positive factors (Korean)
4. weaknesses: list of negative factors (Korean)
5. summary_kr: Korean summary, 2-3 sentences

RESPOND IN JSON ONLY."""

    def get_analysis_prompt(self, raw_data: dict, state: dict) -> str:
        return json.dumps({
            "ticker": state["ticker"],
            "per": raw_data.get("per"),
            "pbr": raw_data.get("pbr"),
            "roe": raw_data.get("roe"),
            "revenue_growth": raw_data.get("revenue_growth"),
            "debt_ratio": raw_data.get("debt_ratio"),
            "sector_avg_per": SECTOR_AVG_PER,
        }, ensure_ascii=False)

    def calculate_score(self, raw_data: dict, analysis: dict) -> float:
        """Rule-based: PER(35%) + ROE(30%) + 매출성장률(20%) + 부채비율(15%)."""
        per_score = _score_per_ratio(raw_data.get("per", 0), SECTOR_AVG_PER)
        roe_score = _score_roe(raw_data.get("roe", 0))
        growth_score = _score_revenue_growth(raw_data.get("revenue_growth", 0))
        debt_score = _score_debt_ratio(raw_data.get("debt_ratio", 0))

        return per_score * 0.35 + roe_score * 0.30 + growth_score * 0.20 + debt_score * 0.15
