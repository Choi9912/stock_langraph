"""Macro Agent — 거시경제 환경 분석 에이전트.

Fetch: yfinance(VIX, 지수) + FRED API(미국 금리) + ECOS(한국 금리, 환율)
Analyze: LLM이 거시환경 종합 판단 (risk_on/risk_off)
Score: Rule-based (VIX 35%, 지수 변동 25%, 금리 방향 25%, 환율 15%)
"""

import json

from agents.base import BaseAgent
from config.settings import FRED_API_KEY
from tools.cache import cached_api_call

# TODO: ECOS API 연동 전까지 하드코딩
BOK_BASE_RATE = 3.00


def _fetch_vix() -> dict | None:
    """yfinance로 VIX + 주요 지수 가져오기."""
    import yfinance as yf

    try:
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="5d")
        vix_current = float(vix_hist["Close"].iloc[-1]) if not vix_hist.empty else 20.0

        # S&P 500 최근 변동
        sp500 = yf.Ticker("^GSPC")
        sp_hist = sp500.history(period="1mo")
        if not sp_hist.empty and len(sp_hist) >= 2:
            sp_current = float(sp_hist["Close"].iloc[-1])
            sp_prev_month = float(sp_hist["Close"].iloc[0])
            sp_change = ((sp_current - sp_prev_month) / sp_prev_month) * 100
        else:
            sp_current, sp_change = 0.0, 0.0

        # KOSPI
        kospi = yf.Ticker("^KS11")
        ks_hist = kospi.history(period="1mo")
        if not ks_hist.empty and len(ks_hist) >= 2:
            ks_current = float(ks_hist["Close"].iloc[-1])
            ks_prev_month = float(ks_hist["Close"].iloc[0])
            ks_change = ((ks_current - ks_prev_month) / ks_prev_month) * 100
        else:
            ks_current, ks_change = 0.0, 0.0

        return {
            "vix": round(vix_current, 2),
            "sp500": round(sp_current, 2),
            "sp500_change_1m": round(sp_change, 2),
            "kospi": round(ks_current, 2),
            "kospi_change_1m": round(ks_change, 2),
        }
    except Exception:
        return None


def _fetch_fred_rates() -> dict | None:
    """FRED API로 미국 금리 가져오기."""
    import requests

    if not FRED_API_KEY:
        return None

    try:
        # Federal Funds Rate
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": "FEDFUNDS",
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 2,
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        obs = data.get("observations", [])

        if len(obs) >= 2:
            current_rate = float(obs[0]["value"])
            prev_rate = float(obs[1]["value"])
            direction = "rising" if current_rate > prev_rate else "falling" if current_rate < prev_rate else "stable"
        elif len(obs) == 1:
            current_rate = float(obs[0]["value"])
            prev_rate = current_rate
            direction = "stable"
        else:
            return None

        return {
            "fed_rate": current_rate,
            "fed_rate_prev": prev_rate,
            "fed_rate_direction": direction,
        }
    except Exception:
        return None


def _fetch_macro_data(market: str) -> dict | None:
    """거시경제 데이터 통합 Fetch."""
    result = {}

    # VIX + 지수 (yfinance)
    vix_data = cached_api_call(
        key="macro:vix_indices",
        fetcher=_fetch_vix,
        ttl_hours=1,
    )
    if vix_data:
        result.update(vix_data)
    else:
        result["vix"] = 20.0  # 기본값

    # FRED 금리
    fred_data = cached_api_call(
        key="macro:fred_rates",
        fetcher=_fetch_fred_rates,
        ttl_hours=12,
    )
    if fred_data:
        result.update(fred_data)
    else:
        result["fed_rate"] = 5.25  # 기본값
        result["fed_rate_direction"] = "stable"

    # 한국 금리 (TODO: ECOS API)
    result["bok_rate"] = BOK_BASE_RATE

    return result if result else None


def _score_vix(vix: float) -> float:
    if vix < 15:
        return 0.85
    elif vix < 20:
        return 0.70
    elif vix < 25:
        return 0.50
    elif vix < 30:
        return 0.30
    else:
        return 0.10


def _score_index_change(change_pct: float) -> float:
    """지수 1개월 변동률 스코어."""
    if change_pct > 5:
        return 0.85
    elif change_pct > 2:
        return 0.70
    elif change_pct > -2:
        return 0.50
    elif change_pct > -5:
        return 0.30
    else:
        return 0.15


def _score_rate_direction(direction: str) -> float:
    """금리 방향 스코어 (인하=호재, 인상=악재)."""
    if direction == "falling":
        return 0.75
    elif direction == "stable":
        return 0.50
    else:
        return 0.25


def _score_exchange_rate(usd_krw_change: float) -> float:
    """환율 변동 스코어 (원화 강세=호재). TODO: 실제 환율 데이터 연동."""
    return 0.50  # 기본값 (데이터 없음)


class MacroAgent(BaseAgent):
    agent_key = "macro"

    def fetch(self, state: dict) -> dict | None:
        market = state["market"]
        return cached_api_call(
            key=f"macro:{market}",
            fetcher=lambda: _fetch_macro_data(market),
            ttl_hours=1,
        )

    def get_system_prompt(self) -> str:
        return """You are a macroeconomic analyst. Given macro indicators, assess:
1. market_regime: "risk_on" | "neutral" | "risk_off"
2. vix_assessment: VIX level interpretation (Korean)
3. rate_outlook: interest rate outlook - "hawkish" | "neutral" | "dovish"
4. key_risks: list of current macro risks (Korean)
5. summary_kr: Korean summary, 2-3 sentences

RESPOND IN JSON ONLY."""

    def get_analysis_prompt(self, raw_data: dict, state: dict) -> str:
        return json.dumps({
            "market": state["market"],
            "vix": raw_data.get("vix"),
            "sp500_change_1m": raw_data.get("sp500_change_1m"),
            "kospi_change_1m": raw_data.get("kospi_change_1m"),
            "fed_rate": raw_data.get("fed_rate"),
            "fed_rate_direction": raw_data.get("fed_rate_direction"),
            "bok_rate": raw_data.get("bok_rate"),
        }, ensure_ascii=False)

    def calculate_score(self, raw_data: dict, analysis: dict) -> float:
        """Rule-based: VIX(35%) + 지수 변동(25%) + 금리 방향(25%) + 환율(15%)."""
        vix_score = _score_vix(raw_data.get("vix", 20.0))

        # 시장에 따라 지수 선택
        index_change = raw_data.get("kospi_change_1m") or raw_data.get("sp500_change_1m") or 0.0
        index_score = _score_index_change(index_change)

        rate_dir = raw_data.get("fed_rate_direction", "stable")
        rate_score = _score_rate_direction(rate_dir)

        fx_score = _score_exchange_rate(0.0)  # TODO

        return vix_score * 0.35 + index_score * 0.25 + rate_score * 0.25 + fx_score * 0.15
