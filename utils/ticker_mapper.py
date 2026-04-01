"""종목명 ↔ 티커 변환.

현재는 주요 종목만 하드코딩. TODO: CSV DB 확장.
"""

# 국내 주요 종목 (종목명 → 티커)
KRX_TICKERS: dict[str, str] = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "LG에너지솔루션": "373220",
    "삼성바이오로직스": "207940",
    "현대차": "005380",
    "현대자동차": "005380",
    "기아": "000270",
    "셀트리온": "068270",
    "KB금융": "105560",
    "신한지주": "055550",
    "POSCO홀딩스": "005490",
    "포스코홀딩스": "005490",
    "NAVER": "035420",
    "네이버": "035420",
    "카카오": "035720",
    "LG화학": "051910",
    "삼성SDI": "006400",
    "현대모비스": "012330",
    "삼성물산": "028260",
    "한국전력": "015760",
}

# 티커 → 종목명 (역매핑, 뉴스 검색용)
KRX_NAMES: dict[str, str] = {}
_seen = set()
for name, code in KRX_TICKERS.items():
    if code not in _seen:
        KRX_NAMES[code] = name
        _seen.add(code)

# 해외 주요 종목
US_TICKERS: dict[str, str] = {
    "애플": "AAPL",
    "apple": "AAPL",
    "마이크로소프트": "MSFT",
    "microsoft": "MSFT",
    "구글": "GOOGL",
    "google": "GOOGL",
    "알파벳": "GOOGL",
    "아마존": "AMZN",
    "amazon": "AMZN",
    "테슬라": "TSLA",
    "tesla": "TSLA",
    "엔비디아": "NVDA",
    "nvidia": "NVDA",
    "메타": "META",
    "meta": "META",
    "코카콜라": "KO",
    "coca-cola": "KO",
    "cocacola": "KO",
    "넷플릭스": "NFLX",
    "netflix": "NFLX",
    "디즈니": "DIS",
    "disney": "DIS",
    "마이크론": "MU",
    "micron": "MU",
    "AMD": "AMD",
    "amd": "AMD",
    "인텔": "INTC",
    "intel": "INTC",
    "JP모건": "JPM",
    "jpmorgan": "JPM",
    "비자": "V",
    "visa": "V",
    "마스터카드": "MA",
    "mastercard": "MA",
    "보잉": "BA",
    "boeing": "BA",
    "나이키": "NKE",
    "nike": "NKE",
    "스타벅스": "SBUX",
    "starbucks": "SBUX",
}


def name_to_ticker(name: str) -> tuple[str, str] | None:
    """종목명 → (티커, 마켓). 없으면 None."""
    normalized = name.strip()

    # 국내
    if normalized in KRX_TICKERS:
        code = KRX_TICKERS[normalized]
        return f"{code}.KS", "KRX"

    # 해외
    lower = normalized.lower()
    if lower in US_TICKERS:
        return US_TICKERS[lower], "NYSE"  # NYSE/NASDAQ 구분은 추후 개선

    # 이미 티커 형태인 경우
    if normalized.upper() == normalized and normalized.isalpha() and len(normalized) <= 5:
        return normalized, "NYSE"

    # 국내 코드 직접 입력 (숫자 6자리)
    if normalized.isdigit() and len(normalized) == 6:
        return f"{normalized}.KS", "KRX"

    return None


def ticker_to_name(ticker: str) -> str:
    """티커 → 종목명 (뉴스 검색용). 없으면 티커 그대로 반환."""
    # 국내: "005930.KS" → "005930"
    code = ticker.replace(".KS", "").replace(".KQ", "")
    if code in KRX_NAMES:
        return KRX_NAMES[code]
    return ticker
