# Stock Advisor

> LangGraph 기반 7개 병렬 AI 에이전트가 종합 매매 시그널을 생성하는 주식 분석 시스템

```
$ python main.py "삼성전자"

# 삼성전자 (005930.KS) 분석 리포트
# 시그널: [+] BUY | 신뢰도: 89.8%
# 종합 스코어: 0.654
```

## Architecture

```
Input Parser (GPT가 종목명 → 티커 변환)
    ├── Price Agent        (기술적 분석: RSI, MACD, 볼린저밴드)
    ├── Fundamental Agent  (펀더멘털: PER, PBR, ROE, 부채비율)
    ├── Disclosure Agent   (공시 분석: DART/SEC EDGAR)
    ├── News Agent         (뉴스 감성 분석: NewsAPI 배치)
    ├── Macro Agent        (거시경제: VIX, 금리, 환율)
    ├── Supply/Demand Agent(수급: 기관/외국인 매매동향)
    └── Consensus Agent    (애널리스트 컨센서스: 목표가, 투자의견)
         ↓
    Validator (품질 검증 + 실패 에이전트만 자동 재시도, 최대 2회)
         ↓
    Synthesizer (종목별 가중치 적용 → 종합 스코어 → 시그널)
         ↓
    Report Generator (마크다운 리포트)
```

## Signal System

| 스코어 | 시그널 |
|---|---|
| 0.80+ | STRONG_BUY |
| 0.65 ~ 0.79 | BUY |
| 0.45 ~ 0.64 | HOLD |
| 0.30 ~ 0.44 | SELL |
| < 0.30 | STRONG_SELL |

## 종목별 가중치 (백테스트 기반 자동 최적화)

과거 3개월(12주) 백테스트를 통해 종목별로 어떤 에이전트가 정확했는지 분석하고, 최적 가중치를 자동 도출합니다.

| 종목 | 상위 가중치 |
|---|---|
| 삼성전자 | consensus 35%, supply_demand 15%, disclosure 13% |
| SK하이닉스 | supply_demand 30%, consensus 20%, disclosure 13% |
| 현대차 | consensus 45%, supply_demand 30%, price 10% |
| NVIDIA | consensus 40%, fundamental 35%, price 5% |
| Tesla | consensus 40%, disclosure 15%, news 15% |

종목별 가중치가 없는 종목은 기간별 기본 가중치를 사용합니다:
- **단기**: 기술적 분석(25%) + 수급(20%) 중심
- **중기**: 펀더멘털(20%) + 컨센서스(20%) 중심
- **장기**: 펀더멘털(30%) + 컨센서스(25%) 중심

## Daily Tracking (자동화)

GitHub Actions로 매일 KOSPI 5 + NASDAQ 5 종목을 자동 분석합니다.

| 스케줄 | 시간 (KST) | 대상 |
|---|---|---|
| 국장 | 평일 16:00 | 삼성전자, SK하이닉스, 현대차, NAVER, 카카오 |
| 미장 | 화~토 07:00 | Apple, NVIDIA, Tesla, Microsoft, Alphabet |
| 가중치 튜닝 | 매주 일요일 | 백테스트 평가 → 가중치 자동 조정 |

결과는 `data/history/YYYY-MM-DD.json`에 자동 커밋됩니다.

```bash
# 기록 조회
python history_viewer.py latest                          # 최근 기록
python history_viewer.py history --ticker 삼성전자         # 종목별 추이
python history_viewer.py compare --day1 2026-04-01 --day2 2026-04-08  # 날짜 비교
```

## 가중치 자동 튜닝

매주 백테스트를 통해 가중치를 자동으로 조정합니다:

1. 과거 시그널과 실제 수익률 비교
2. 에이전트별 정확도 + 상관계수 계산
3. 정확한 에이전트 → 가중치 UP, 부정확 → DOWN
4. 종목별 보정값 업데이트

```bash
# 수동 실행
python -m tools.historical_backtest --weeks 12    # 과거 백테스트
python -m tools.weight_tuner tune --days 10       # 가중치 튜닝
python -m tools.weight_tuner apply                # settings.py에 반영
```

## Example Results (2026-04-01)

| 종목 | 시그널 | 스코어 | 신뢰도 | 현재가 | 목표가 |
|---|---|---|---|---|---|
| 삼성전자 | **BUY** | 0.654 | 89.8% | 189,600 | 239,873 |
| SK하이닉스 | HOLD | 0.641 | 85.8% | 893,000 | 1,320,166 |
| NAVER | HOLD | 0.609 | 87.5% | 210,000 | 325,885 |
| Alphabet | HOLD | 0.566 | 88.5% | 288 | 377 |
| Microsoft | HOLD | 0.560 | 91.5% | 370 | 590 |
| NVIDIA | HOLD | 0.540 | 91.6% | 174 | 268 |
| Tesla | HOLD | 0.481 | 94.8% | 372 | 421 |

## Tech Stack

- **Framework**: [LangGraph](https://github.com/langchain-ai/langgraph) (StateGraph, 병렬 fan-out/fan-in)
- **LLM**: GPT-4o-mini (분석 1회당 약 2원)
- **Data**: yfinance, pykrx, DART OpenAPI, Alpha Vantage, NewsAPI, FRED
- **CI/CD**: GitHub Actions (매일 자동 분석 + 매주 가중치 튜닝)
- **Language**: Python 3.12

## Project Structure

```
stock-advisor/
├── main.py                     # 단일 종목 분석 진입점
├── daily_tracker.py            # 매일 10종목 자동 분석
├── history_viewer.py           # 기록 조회 + 추이 비교
├── graph/
│   ├── state.py                # StockAnalysisState
│   ├── graph.py                # LangGraph (7 에이전트 병렬 + retry)
│   └── edges.py                # Conditional edge 라우팅
├── agents/
│   ├── base.py                 # BaseAgent (Fetch→Analyze→Score)
│   ├── input_parser.py         # GPT 기반 종목명→티커 변환
│   ├── price_agent.py          # 기술적 분석
│   ├── fundamental_agent.py    # 펀더멘털 분석
│   ├── disclosure_agent.py     # 공시 분석
│   ├── news_agent.py           # 뉴스 감성 분석
│   ├── macro_agent.py          # 거시경제 분석
│   ├── supply_demand_agent.py  # 수급 분석
│   ├── consensus_agent.py      # 애널리스트 컨센서스
│   ├── validator.py            # 품질 검증 + 재시도
│   ├── synthesizer.py          # 종합 스코어 → 시그널
│   └── report_generator.py     # 마크다운 리포트
├── tools/
│   ├── cache.py                # TTL 기반 파일 캐시
│   ├── backtest_evaluator.py   # 시그널 vs 실제 수익률 평가
│   ├── weight_tuner.py         # 가중치 자동 조정
│   └── historical_backtest.py  # 과거 백테스트 시뮬레이션
├── utils/
│   ├── ticker_mapper.py        # 종목명 ↔ 티커
│   └── score_calculator.py     # 종목별/기간별 가중치 적용
├── config/
│   └── settings.py             # 가중치, 시그널 기준, API 키
├── data/
│   ├── history/                # 매일 분석 기록 (JSON)
│   ├── backtest/               # 백테스트 결과 + 종목별 가중치
│   └── tuning/                 # 가중치 튜닝 히스토리
├── .github/workflows/
│   ├── daily_tracker.yml       # 매일 자동 분석
│   └── weekly_tuning.yml       # 매주 가중치 튜닝
└── tests/
```

## Getting Started

### Prerequisites

- Python 3.12+
- OpenAI API Key

### Installation

```bash
git clone https://github.com/Choi9912/stock_langraph.git
cd stock_langraph
pip install -r requirements.txt
```

### Configuration

`.env` 파일을 생성합니다:

```env
OPENAI_API_KEY=sk-your-key-here

# Optional (없어도 기본 동작 — yfinance fallback)
ALPHA_VANTAGE_KEY=your-key
NEWSAPI_KEY=your-key
FRED_API_KEY=your-key
DART_API_KEY=your-key
```

### Usage

```bash
# 단일 종목 분석
python main.py "삼성전자"
python main.py "코카콜라 장기 분석"
python main.py "NVDA"

# 매일 트래킹
python daily_tracker.py                  # 전체 (KOSPI + NASDAQ)
python daily_tracker.py --market krx     # 국장만
python daily_tracker.py --market us      # 미장만

# 기록 조회
python history_viewer.py latest
python history_viewer.py history --ticker 삼성전자 --days 30

# 백테스트 + 가중치 튜닝
python -m tools.historical_backtest --weeks 12
python -m tools.weight_tuner tune
python -m tools.weight_tuner apply
```

---

*본 시스템의 출력은 참고용이며, 실제 매매 결정의 책임은 사용자에게 있습니다.*
