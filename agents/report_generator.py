"""Report Generator — 최종 마크다운 리포트 생성."""

from datetime import datetime

from utils.ticker_mapper import ticker_to_name

PERIOD_LABEL = {"short": "단기 (20일)", "mid": "중기 (90일)", "long": "장기 (1년)"}

SIGNAL_EMOJI = {
    "STRONG_BUY": "[++]",
    "BUY": "[+]",
    "HOLD": "[=]",
    "SELL": "[-]",
    "STRONG_SELL": "[--]",
}


def generate_report(state: dict) -> dict:
    """State로부터 최종 마크다운 리포트 생성."""
    ticker = state.get("ticker", "N/A")
    market = state.get("market", "N/A")
    period = state.get("analysis_period", "short")
    signal = state.get("signal", "HOLD")
    confidence = state.get("confidence", 0.0)
    reasoning = state.get("reasoning", "")
    risk_factors = state.get("risk_factors", [])
    agent_results = state.get("agent_results", {})
    error_log = state.get("error_log", [])

    name = ticker_to_name(ticker)
    period_label = PERIOD_LABEL.get(period, period)
    sig_icon = SIGNAL_EMOJI.get(signal, "")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# {name} ({ticker}) 분석 리포트",
        f"",
        f"- **일시**: {now}",
        f"- **시장**: {market}",
        f"- **분석 기간**: {period_label}",
        f"- **시그널**: {sig_icon} **{signal}**",
        f"- **신뢰도**: {confidence:.1%}",
        f"",
        f"---",
        f"",
        f"## 종합 판단",
        f"",
    ]

    for line in reasoning.split("\n"):
        lines.append(f"- {line}")

    lines.extend(["", "---", "", "## 개별 에이전트 결과", ""])

    agent_labels = {
        "price": "기술적 분석 (Price)",
        "fundamental": "펀더멘털 (Fundamental)",
        "disclosure": "공시 (Disclosure)",
        "news": "뉴스 (News)",
        "macro": "거시경제 (Macro)",
        "supply_demand": "수급 분석 (Supply/Demand)",
        "consensus": "애널리스트 컨센서스 (Consensus)",
    }

    for key, label in agent_labels.items():
        result = agent_results.get(key, {})
        score = result.get("score", 0.0)
        bar = _score_bar(score)
        lines.append(f"### {label}")

        if "error" in result:
            lines.append(f"- **스코어**: {score:.2f} {bar}")
            lines.append(f"- **오류**: {result['error']}")
        else:
            lines.append(f"- **스코어**: {score:.2f} {bar}")
            analysis = result.get("analysis", {})
            summary = analysis.get("summary_kr", "")
            if summary:
                lines.append(f"- **요약**: {summary}")

        lines.append("")

    if risk_factors:
        lines.extend(["---", "", "## 리스크 요인", ""])
        for rf in risk_factors:
            lines.append(f"- {rf}")
        lines.append("")

    if error_log:
        lines.extend(["---", "", "## 오류 로그", ""])
        for err in error_log:
            lines.append(f"- {err}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "*본 시스템의 출력은 참고용이며, 실제 매매 결정의 책임은 사용자에게 있습니다.*",
    ])

    return {"final_report": "\n".join(lines)}


def _score_bar(score: float, width: int = 10) -> str:
    """스코어를 시각적 바로 변환."""
    filled = int(score * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"
