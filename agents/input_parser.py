"""사용자 입력을 파싱하여 ticker, market, analysis_period를 추출.

LLM이 종목명 → 티커 심볼 변환까지 직접 수행.
"""

from langchain_openai import ChatOpenAI

from agents.base import parse_json_response
from config.settings import LLM_MODEL, OPENAI_API_KEY

SYSTEM_PROMPT = """You are a stock analysis input parser. Extract the following from user input:

1. ticker: The stock ticker symbol for Yahoo Finance (e.g., "AAPL", "TSLA", "KO", "005930.KS")
   - For Korean stocks (KRX), append ".KS" suffix (e.g., "삼성전자" → "005930.KS", "SK하이닉스" → "000660.KS")
   - For US stocks, use the standard ticker (e.g., "코카콜라" → "KO", "테슬라" → "TSLA")
2. market: "KRX" for Korean stocks, "NYSE" or "NASDAQ" for US stocks
3. company_name: The company name (for news search)
4. period: "short" (days~weeks), "mid" (weeks~months), or "long" (months~year)

If period is ambiguous, default to "short".

RESPOND IN JSON ONLY:
{"ticker": "...", "market": "...", "company_name": "...", "period": "short|mid|long"}"""


def parse_input(state: dict) -> dict:
    """사용자 raw_input → ticker, market, analysis_period 추출."""
    # ticker가 이미 설정되어 있으면 LLM 호출 스킵
    if state.get("ticker"):
        return {}

    raw_input = state["raw_input"]

    llm = ChatOpenAI(model=LLM_MODEL, api_key=OPENAI_API_KEY, temperature=0)
    response = llm.invoke([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": raw_input},
    ])

    parsed = parse_json_response(response.content)
    ticker = parsed.get("ticker", "")
    market = parsed.get("market", "KRX")
    period = parsed.get("period", "short")

    if period not in ("short", "mid", "long"):
        period = "short"

    if not ticker:
        return {
            "error_log": [f"input_parser: 종목을 찾을 수 없음: {raw_input}"],
            "ticker": "",
            "market": market,
            "analysis_period": period,
        }

    return {
        "ticker": ticker,
        "market": market,
        "analysis_period": period,
    }
