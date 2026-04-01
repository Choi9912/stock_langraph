"""그래프 통합 테스트 — mock 모드."""

import os

os.environ["USE_MOCK"] = "true"

import pytest


def _initial_state(raw_input="삼성전자 단기 분석"):
    return {
        "raw_input": raw_input,
        "ticker": "",
        "market": "KRX",
        "analysis_period": "short",
        "agent_results": {},
        "validation_result": {},
        "retry_targets": [],
        "retry_count": 0,
        "signal": "HOLD",
        "confidence": 0.0,
        "reasoning": "",
        "risk_factors": [],
        "final_report": "",
        "messages": [],
        "error_log": [],
    }


class TestFullGraph:
    def test_e2e_samsung(self):
        from graph.graph import app

        result = app.invoke(_initial_state("삼성전자 단기 분석"))

        assert result["ticker"] == "005930.KS"
        assert result["market"] == "KRX"
        assert result["signal"] in ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"]
        assert 0.0 <= result["confidence"] <= 1.0
        assert result["final_report"]
        assert "삼성전자" in result["final_report"]

    def test_e2e_aapl(self):
        from graph.graph import app

        result = app.invoke(_initial_state("애플 장기 투자 분석"))

        assert result["ticker"] == "AAPL"
        assert result["signal"] in ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"]
        assert result["final_report"]

    def test_all_agents_present(self):
        from graph.graph import app

        result = app.invoke(_initial_state("삼성전자 분석"))
        agent_results = result["agent_results"]

        for key in ["price", "fundamental", "disclosure", "news", "macro"]:
            assert key in agent_results, f"{key} agent missing"
            assert "score" in agent_results[key]

    def test_report_contains_disclaimer(self):
        from graph.graph import app

        result = app.invoke(_initial_state("삼성전자 분석"))
        assert "책임은 사용자에게" in result["final_report"]


class TestValidator:
    def test_all_pass(self):
        from agents.validator import validate

        state = {
            "agent_results": {
                "price": {"score": 0.5},
                "fundamental": {"score": 0.6},
                "disclosure": {"score": 0.4},
                "news": {"score": 0.7},
                "macro": {"score": 0.5},
            },
            "retry_count": 0,
        }
        result = validate(state)
        assert result["validation_result"]["passed"] is True
        assert result["retry_targets"] == []

    def test_missing_agent_triggers_retry(self):
        from agents.validator import validate

        state = {
            "agent_results": {
                "price": {"score": 0.5},
                # fundamental missing
                "disclosure": {"score": 0.4},
                "news": {"score": 0.7},
                "macro": {"score": 0.5},
            },
            "retry_count": 0,
        }
        result = validate(state)
        assert result["validation_result"]["passed"] is False
        assert "fundamental" in result["retry_targets"]

    def test_max_retry_stops(self):
        from agents.validator import validate

        state = {
            "agent_results": {"price": {"score": 0.5, "error": "fail"}},
            "retry_count": 2,
        }
        result = validate(state)
        assert result["retry_targets"] == []  # max retry reached


class TestSynthesizer:
    def test_signal_generation(self):
        from agents.synthesizer import synthesize

        state = {
            "agent_results": {
                "price": {"score": 0.85},
                "fundamental": {"score": 0.90},
                "disclosure": {"score": 0.80},
                "news": {"score": 0.85},
                "macro": {"score": 0.80},
            },
            "analysis_period": "short",
            "validation_result": {},
        }
        result = synthesize(state)
        assert result["signal"] in ["STRONG_BUY", "BUY"]
        assert result["confidence"] > 0.5

    def test_low_scores_give_sell(self):
        from agents.synthesizer import synthesize

        state = {
            "agent_results": {
                "price": {"score": 0.15},
                "fundamental": {"score": 0.20},
                "disclosure": {"score": 0.10},
                "news": {"score": 0.15},
                "macro": {"score": 0.10},
            },
            "analysis_period": "short",
            "validation_result": {},
        }
        result = synthesize(state)
        assert result["signal"] in ["STRONG_SELL", "SELL"]


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
        # short에서는 price 비중 높아서 점수 높음
        assert short > long_

    def test_score_to_signal(self):
        from utils.score_calculator import score_to_signal

        assert score_to_signal(0.85) == "STRONG_BUY"
        assert score_to_signal(0.70) == "BUY"
        assert score_to_signal(0.50) == "HOLD"
        assert score_to_signal(0.35) == "SELL"
        assert score_to_signal(0.20) == "STRONG_SELL"
