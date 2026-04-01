"""News Agent — 뉴스 감성 분석 에이전트.

Fetch: NewsAPI + 네이버 RSS → 최근 7일 뉴스, 최대 20건
Analyze: LLM 배치 감성 분석 (20건 한 번에, API 1회)
Score: Rule-based (positive_ratio 가중 + 속보 보정)
"""

import json
from datetime import datetime, timedelta

from agents.base import BaseAgent
from config.settings import NEWSAPI_KEY
from tools.cache import cached_api_call
from utils.ticker_mapper import ticker_to_name


def _fetch_newsapi(query: str) -> list[dict] | None:
    """NewsAPI로 뉴스 검색."""
    import requests

    if not NEWSAPI_KEY:
        return None

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
        "sortBy": "relevancy",
        "pageSize": 20,
        "language": "ko",
        "apiKey": NEWSAPI_KEY,
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        articles = data.get("articles", [])
        return [
            {
                "title": a.get("title", ""),
                "description": (a.get("description") or "")[:150],
                "source": a.get("source", {}).get("name", ""),
                "published_at": a.get("publishedAt", ""),
            }
            for a in articles[:20]
        ]
    except Exception:
        return None


def _fetch_naver_rss(query: str) -> list[dict] | None:
    """네이버 뉴스 RSS 검색 (폴백)."""
    import requests
    import xml.etree.ElementTree as ET

    url = "https://news.google.com/rss/search"
    params = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}

    try:
        resp = requests.get(url, params=params, timeout=10)
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")[:20]

        return [
            {
                "title": item.findtext("title", ""),
                "description": (item.findtext("description") or "")[:150],
                "source": item.findtext("source", ""),
                "published_at": item.findtext("pubDate", ""),
            }
            for item in items
        ]
    except Exception:
        return None


def _fetch_news(ticker: str, market: str) -> dict | None:
    """뉴스 데이터 통합 Fetch."""
    # 국내 주식은 티커 대신 회사명으로 검색
    query = ticker_to_name(ticker)

    articles = _fetch_newsapi(query)
    if not articles:
        articles = _fetch_naver_rss(query)
    if not articles:
        return None

    return {
        "ticker": ticker,
        "query": query,
        "articles": articles,
        "count": len(articles),
    }


class NewsAgent(BaseAgent):
    agent_key = "news"

    def fetch(self, state: dict) -> dict | None:
        ticker = state["ticker"]
        market = state["market"]

        return cached_api_call(
            key=f"news:{ticker}",
            fetcher=lambda: _fetch_news(ticker, market),
            ttl_hours=2,
        )

    def get_system_prompt(self) -> str:
        return """You are a financial news sentiment analyst. For each news article (title + description), classify sentiment.

For each article provide:
- title: original title
- sentiment: "positive" | "negative" | "neutral"

Then provide aggregate:
- positive_count, negative_count, neutral_count
- has_breaking: true if any article appears to be breaking/urgent news
- summary_kr: Korean summary, 2-3 sentences

RESPOND IN JSON ONLY:
{"sentiments": [{"title": "...", "sentiment": "positive"}], "positive_count": 5, "negative_count": 2, "neutral_count": 3, "has_breaking": false, "summary_kr": "..."}

Process ALL articles in a SINGLE batch. Do NOT call separately for each article."""

    def get_analysis_prompt(self, raw_data: dict, state: dict) -> str:
        # 제목+설명만 전달 (토큰 절약)
        articles = [
            {"title": a["title"], "description": a.get("description", "")}
            for a in raw_data.get("articles", [])
        ]
        return json.dumps({
            "ticker": state["ticker"],
            "article_count": len(articles),
            "articles": articles,
        }, ensure_ascii=False)

    def calculate_score(self, raw_data: dict, analysis: dict) -> float:
        """Rule-based: positive_ratio 가중 + 속보 보정."""
        pos = analysis.get("positive_count", 0)
        neg = analysis.get("negative_count", 0)
        total = pos + neg + analysis.get("neutral_count", 0)

        if total == 0:
            return 0.5

        positive_ratio = pos / total
        negative_ratio = neg / total

        base_score = 0.5 + (positive_ratio - negative_ratio) * 0.4
        breaking_boost = 0.05 if analysis.get("has_breaking", False) else 0.0

        return max(0.0, min(1.0, base_score + breaking_boost))
