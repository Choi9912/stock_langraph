"""Disclosure Agent — 공시 분석 에이전트.

Fetch: DART OpenAPI(국내) / SEC EDGAR(해외) → 최근 30일 공시 목록 (최대 15건)
Analyze: LLM이 각 공시 1줄 요약 + 투자 영향도 판단
Score: LLM-scored (유일한 예외 — 공시 맥락은 rule로 판단 불가)
"""

import json
from datetime import datetime, timedelta

from agents.base import BaseAgent
from config.settings import DART_API_KEY
from tools.cache import cached_api_call


def _fetch_dart_disclosures(ticker: str) -> dict | None:
    """DART OpenAPI로 최근 공시 목록 가져오기."""
    if not DART_API_KEY:
        return {"ticker": ticker, "disclosures": [], "source": "DART_NO_KEY"}

    import opendartreader as dart

    api = dart.OpenDartReader(DART_API_KEY)
    code = ticker.replace(".KS", "").replace(".KQ", "")

    try:
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        disclosures = api.list(code, start=start, end=end)

        if disclosures is None or disclosures.empty:
            return {"ticker": ticker, "disclosures": [], "source": "DART"}

        items = []
        for _, row in disclosures.head(15).iterrows():
            items.append({
                "title": row.get("report_nm", ""),
                "date": row.get("rcept_dt", ""),
                "type": row.get("pblntf_ty", ""),
            })

        return {"ticker": ticker, "disclosures": items, "source": "DART"}
    except Exception:
        return None


def _fetch_sec_edgar(ticker: str) -> dict | None:
    """SEC EDGAR에서 최근 공시 가져오기. TODO: 폴백 로직 보완."""
    import requests

    headers = {"User-Agent": "StockAdvisor/1.0 contact@example.com"}
    url = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt={(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')}&enddt={datetime.now().strftime('%Y-%m-%d')}"

    try:
        resp = requests.get(
            f"https://efts.sec.gov/LATEST/search-index?q={ticker}&forms=10-K,10-Q,8-K,4",
            headers=headers,
            timeout=10,
        )
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])[:15]

        items = []
        for hit in hits:
            src = hit.get("_source", {})
            items.append({
                "title": src.get("display_names", [""])[0] if src.get("display_names") else src.get("form_type", ""),
                "date": src.get("file_date", ""),
                "type": src.get("form_type", ""),
            })

        return {"ticker": ticker, "disclosures": items, "source": "SEC_EDGAR"}
    except Exception:
        return None


# LLM 프롬프트에 포함할 시그널 가이드
SIGNAL_GUIDE = """
Signal guide for scoring (-1.0 to +1.0):
- 자사주 매입 / Stock buyback → +0.5 to +0.8
- 유상증자 / Secondary offering → -0.3 to -0.7
- 실적 서프라이즈 / Earnings beat → +0.6 to +0.9
- 대주주 지분 매각 / Insider selling → -0.4 to -0.6
- Insider buying (Form 4) → +0.3 to +0.5
- 일반 보고서 / Regular filing → -0.1 to +0.1
"""


class DisclosureAgent(BaseAgent):
    agent_key = "disclosure"

    def fetch(self, state: dict) -> dict | None:
        ticker = state["ticker"]
        market = state["market"]

        if market == "KRX":
            fetcher = lambda: _fetch_dart_disclosures(ticker)
        else:
            fetcher = lambda: _fetch_sec_edgar(ticker)

        return cached_api_call(
            key=f"disclosure:{ticker}",
            fetcher=fetcher,
            ttl_hours=6,
        )

    def get_system_prompt(self) -> str:
        return f"""You are a disclosure/filing analysis expert. For each disclosure item, provide:
1. summary: one-line summary (Korean for KRX, English for US)
2. impact: investment impact score from -1.0 (very negative) to +1.0 (very positive)

{SIGNAL_GUIDE}

Then provide:
- overall_impact: weighted average of all impacts (-1.0 to +1.0)
- summary_kr: Korean summary, 2-3 sentences

RESPOND IN JSON ONLY:
{{"items": [{{"title": "...", "summary": "...", "impact": 0.5}}], "overall_impact": 0.3, "summary_kr": "..."}}"""

    def get_analysis_prompt(self, raw_data: dict, state: dict) -> str:
        return json.dumps({
            "ticker": state["ticker"],
            "market": state["market"],
            "disclosures": raw_data.get("disclosures", []),
        }, ensure_ascii=False)

    def calculate_score(self, raw_data: dict, analysis: dict) -> float:
        """LLM-scored: overall_impact (-1.0~+1.0)을 0.0~1.0으로 변환."""
        impact = analysis.get("overall_impact", 0.0)
        try:
            impact = float(impact)
        except (TypeError, ValueError):
            impact = 0.0
        # -1.0~+1.0 → 0.0~1.0
        return (impact + 1.0) / 2.0
