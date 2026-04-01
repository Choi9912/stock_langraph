"""Price Agent — 기술적 분석 에이전트.

Fetch: yfinance(해외) / pykrx(국내) → OHLCV + pandas_ta 지표
Analyze: LLM이 지표 조합 해석
Score: Rule-based (RSI 30%, MACD 25%, MA 정배열 25%, BB 위치 20%)
"""

import json

import pandas as pd

from agents.base import BaseAgent
from tools.cache import cached_api_call


def _fetch_yfinance(ticker: str) -> dict | None:
    """yfinance로 OHLCV 데이터 가져오기."""
    import yfinance as yf

    stock = yf.Ticker(ticker)
    df = stock.history(period="3mo")
    if df.empty:
        return None
    return {
        "ticker": ticker,
        "close": df["Close"].tolist(),
        "open": df["Open"].tolist(),
        "high": df["High"].tolist(),
        "low": df["Low"].tolist(),
        "volume": df["Volume"].tolist(),
    }


def _fetch_pykrx(ticker: str) -> dict | None:
    """pykrx로 국내 OHLCV 데이터 가져오기."""
    from datetime import datetime, timedelta

    from pykrx import stock as pykrx_stock

    code = ticker.replace(".KS", "").replace(".KQ", "")
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
    df = pykrx_stock.get_market_ohlcv_by_date(start, end, code)
    if df.empty:
        return None
    return {
        "ticker": ticker,
        "close": df["종가"].tolist(),
        "open": df["시가"].tolist(),
        "high": df["고가"].tolist(),
        "low": df["저가"].tolist(),
        "volume": df["거래량"].tolist(),
    }


def compute_indicators(raw_data: dict) -> dict:
    """pandas_ta로 기술적 지표 계산."""
    import pandas_ta as ta

    df = pd.DataFrame({
        "close": raw_data["close"],
        "open": raw_data["open"],
        "high": raw_data["high"],
        "low": raw_data["low"],
        "volume": raw_data["volume"],
    })

    # RSI (14)
    rsi_series = ta.rsi(df["close"], length=14)
    rsi = float(rsi_series.iloc[-1]) if rsi_series is not None and not rsi_series.empty else 50.0

    # MACD (12, 26, 9)
    macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd_df is not None and not macd_df.empty:
        macd_val = float(macd_df.iloc[-1, 0])  # MACD line
        macd_signal = float(macd_df.iloc[-1, 1])  # Signal line
        macd_hist = float(macd_df.iloc[-1, 2])  # Histogram
    else:
        macd_val, macd_signal, macd_hist = 0.0, 0.0, 0.0

    # Bollinger Bands (20, 2)
    bb_df = ta.bbands(df["close"], length=20, std=2)
    if bb_df is not None and not bb_df.empty:
        bb_upper = float(bb_df.iloc[-1, 0])
        bb_mid = float(bb_df.iloc[-1, 1])
        bb_lower = float(bb_df.iloc[-1, 2])
    else:
        bb_upper, bb_mid, bb_lower = 0.0, 0.0, 0.0

    # Moving Averages
    closes = df["close"]
    current_price = float(closes.iloc[-1])
    ma5 = float(closes.rolling(5).mean().iloc[-1]) if len(closes) >= 5 else current_price
    ma20 = float(closes.rolling(20).mean().iloc[-1]) if len(closes) >= 20 else current_price
    ma60 = float(closes.rolling(60).mean().iloc[-1]) if len(closes) >= 60 else current_price

    return {
        "current_price": current_price,
        "rsi": round(rsi, 2),
        "macd": round(macd_val, 4),
        "macd_signal": round(macd_signal, 4),
        "macd_hist": round(macd_hist, 4),
        "bb_upper": round(bb_upper, 2),
        "bb_mid": round(bb_mid, 2),
        "bb_lower": round(bb_lower, 2),
        "ma5": round(ma5, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
    }


def _score_rsi(rsi: float) -> float:
    if rsi <= 30:
        return 0.85
    elif rsi <= 45:
        return 0.70
    elif rsi <= 55:
        return 0.50
    elif rsi <= 70:
        return 0.35
    else:
        return 0.15


def _score_macd_hist(macd_hist: float) -> float:
    if macd_hist > 0.5:
        return 0.85
    elif macd_hist > 0:
        return 0.65
    elif macd_hist > -0.5:
        return 0.35
    else:
        return 0.15


def _score_ma_alignment(price: float, ma5: float, ma20: float, ma60: float) -> float:
    if price > ma5 > ma20 > ma60:
        return 0.85  # 완전 정배열
    elif price > ma20 > ma60:
        return 0.70  # 부분 정배열
    elif price > ma20:
        return 0.50
    elif price < ma5 < ma20 < ma60:
        return 0.15  # 완전 역배열
    else:
        return 0.35


def _score_bb_position(price: float, bb_upper: float, bb_mid: float, bb_lower: float) -> float:
    if bb_upper == bb_lower:
        return 0.50
    position = (price - bb_lower) / (bb_upper - bb_lower)
    if position <= 0.2:
        return 0.80  # 하단 근접 → 매수 기회
    elif position <= 0.4:
        return 0.65
    elif position <= 0.6:
        return 0.50
    elif position <= 0.8:
        return 0.35
    else:
        return 0.20  # 상단 근접 → 과매수


class PriceAgent(BaseAgent):
    agent_key = "price"

    def fetch(self, state: dict) -> dict | None:
        ticker = state["ticker"]
        market = state["market"]

        if market == "KRX":
            fetcher = lambda: _fetch_pykrx(ticker)
        else:
            fetcher = lambda: _fetch_yfinance(ticker)

        raw_data = cached_api_call(
            key=f"price:{ticker}",
            fetcher=fetcher,
            ttl_hours=0.5,
        )

        if raw_data is None:
            return None

        # 지표 계산 (Fetch 단계의 일부, LLM 사용 아님)
        indicators = compute_indicators(raw_data)
        raw_data["indicators"] = indicators
        return raw_data

    def get_system_prompt(self) -> str:
        return """You are a technical analysis expert. Given technical indicators, assess:
1. trend: "uptrend" | "downtrend" | "sideways"
2. macd_interpretation: "bullish_crossover" | "bearish_crossover" | "neutral"
3. bb_position: "upper" | "middle" | "lower" | "squeeze"
4. support_level: estimated support price (number)
5. resistance_level: estimated resistance price (number)
6. summary_kr: Korean summary, 2-3 sentences

RESPOND IN JSON ONLY."""

    def get_analysis_prompt(self, raw_data: dict, state: dict) -> str:
        ind = raw_data["indicators"]
        return json.dumps({
            "ticker": state["ticker"],
            "period": state["analysis_period"],
            "current_price": ind["current_price"],
            "rsi": ind["rsi"],
            "macd": ind["macd"],
            "macd_signal": ind["macd_signal"],
            "macd_hist": ind["macd_hist"],
            "bb_upper": ind["bb_upper"],
            "bb_mid": ind["bb_mid"],
            "bb_lower": ind["bb_lower"],
            "ma5": ind["ma5"],
            "ma20": ind["ma20"],
            "ma60": ind["ma60"],
        }, ensure_ascii=False)

    def calculate_score(self, raw_data: dict, analysis: dict) -> float:
        """Rule-based: RSI(30%) + MACD(25%) + MA(25%) + BB(20%)."""
        ind = raw_data["indicators"]

        rsi_score = _score_rsi(ind["rsi"])
        macd_score = _score_macd_hist(ind["macd_hist"])
        ma_score = _score_ma_alignment(
            ind["current_price"], ind["ma5"], ind["ma20"], ind["ma60"]
        )
        bb_score = _score_bb_position(
            ind["current_price"], ind["bb_upper"], ind["bb_mid"], ind["bb_lower"]
        )

        return rsi_score * 0.30 + macd_score * 0.25 + ma_score * 0.25 + bb_score * 0.20


price_agent = PriceAgent()
price_agent_node = price_agent.run
