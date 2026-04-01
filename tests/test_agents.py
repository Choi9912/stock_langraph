"""에이전트 유닛 테스트 — Rule-based 스코어링 검증."""

import pytest


class TestPriceScoreRules:
    def test_rsi_scores(self):
        from agents.price_agent import _score_rsi

        assert _score_rsi(25) == 0.85  # 과매도
        assert _score_rsi(50) == 0.50  # 중립
        assert _score_rsi(75) == 0.15  # 과매수

    def test_ma_alignment(self):
        from agents.price_agent import _score_ma_alignment

        assert _score_ma_alignment(100, 90, 80, 70) == 0.85  # 완전 정배열
        assert _score_ma_alignment(50, 60, 70, 80) == 0.15  # 완전 역배열

    def test_bb_position(self):
        from agents.price_agent import _score_bb_position

        assert _score_bb_position(100, 100, 100, 100) == 0.50  # bb_upper == bb_lower


class TestFundamentalScoreRules:
    def test_per_ratio(self):
        from agents.fundamental_agent import _score_per_ratio

        assert _score_per_ratio(9.0, 18.0) == 0.90   # ratio 0.5
        assert _score_per_ratio(18.0, 18.0) == 0.40   # ratio 1.0
        assert _score_per_ratio(0, 0) == 0.5           # sector_avg 0

    def test_roe(self):
        from agents.fundamental_agent import _score_roe

        assert _score_roe(25) == 0.90
        assert _score_roe(3) == 0.20


class TestNewsScoreFormula:
    def test_all_positive(self):
        from agents.news_agent import NewsAgent

        agent = NewsAgent()
        score = agent.calculate_score({}, {
            "positive_count": 10, "negative_count": 0, "neutral_count": 0,
            "has_breaking": False,
        })
        assert score == pytest.approx(0.9, abs=0.01)

    def test_all_negative(self):
        from agents.news_agent import NewsAgent

        agent = NewsAgent()
        score = agent.calculate_score({}, {
            "positive_count": 0, "negative_count": 10, "neutral_count": 0,
            "has_breaking": False,
        })
        assert score == pytest.approx(0.1, abs=0.01)

    def test_breaking_boost(self):
        from agents.news_agent import NewsAgent

        agent = NewsAgent()
        score = agent.calculate_score({}, {
            "positive_count": 5, "negative_count": 5, "neutral_count": 0,
            "has_breaking": True,
        })
        assert score == pytest.approx(0.55, abs=0.01)


class TestMacroScoreRules:
    def test_vix(self):
        from agents.macro_agent import _score_vix

        assert _score_vix(12) == 0.85
        assert _score_vix(22) == 0.50
        assert _score_vix(35) == 0.10

    def test_index_change(self):
        from agents.macro_agent import _score_index_change

        assert _score_index_change(6) == 0.85
        assert _score_index_change(0) == 0.50
        assert _score_index_change(-6) == 0.15


class TestBaseAgent:
    def test_validate_score_clamp(self):
        from agents.base import BaseAgent

        assert BaseAgent.validate_score(1.5) == 1.0
        assert BaseAgent.validate_score(-0.3) == 0.0
        assert BaseAgent.validate_score(0.75) == 0.75
        assert BaseAgent.validate_score("invalid") == 0.0
        assert BaseAgent.validate_score(None) == 0.0


class TestScoreCalculator:
    def test_weighted_score_varies_by_period(self):
        from utils.score_calculator import calculate_weighted_score

        scores = {
            "price": 0.9,
            "fundamental": 0.1,
            "disclosure": 0.5,
            "news": 0.5,
            "macro": 0.5,
        }
        short = calculate_weighted_score(scores, "short")
        long_ = calculate_weighted_score(scores, "long")
        assert short > long_

    def test_score_to_signal(self):
        from utils.score_calculator import score_to_signal

        assert score_to_signal(0.85) == "STRONG_BUY"
        assert score_to_signal(0.70) == "BUY"
        assert score_to_signal(0.50) == "HOLD"
        assert score_to_signal(0.35) == "SELL"
        assert score_to_signal(0.20) == "STRONG_SELL"
