"""History Viewer — 기록 조회 + 시그널 변화 추이."""

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HISTORY_DIR = Path("data/history")


def list_records() -> list[Path]:
    """기록 파일 목록 (날짜순)."""
    return sorted(HISTORY_DIR.glob("*.json"))


def load_record(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def show_latest() -> None:
    """가장 최근 기록 출력."""
    records = list_records()
    if not records:
        print("기록이 없습니다. python daily_tracker.py 를 먼저 실행하세요.")
        return

    record = load_record(records[-1])
    _print_record(record)


def show_history(ticker: str = None, days: int = 7) -> None:
    """특정 종목 또는 전체의 최근 N일 기록."""
    records = list_records()[-days:]
    if not records:
        print("기록이 없습니다.")
        return

    if ticker:
        _show_ticker_history(ticker, records)
    else:
        _show_all_history(records)


def _print_record(record: dict) -> None:
    """단일 기록 출력."""
    print(f"\n날짜: {record['date']} (기간: {record['period']})")
    print(f"{'='*75}")
    print(f"{'종목':<12} {'시그널':<12} {'스코어':>8} {'신뢰도':>8} {'현재가':>12} {'목표가':>12}")
    print(f"{'-'*75}")
    for s in sorted(record["stocks"], key=lambda x: x["weighted_score"], reverse=True):
        print(f"{s['name']:<12} {s['signal']:<12} {s['weighted_score']:>8.3f} {s['confidence']:>7.1%} {s['current_price']:>12,.0f} {s['target_mean']:>12,.0f}")
    print(f"{'='*75}")


def _show_ticker_history(ticker: str, record_paths: list[Path]) -> None:
    """특정 종목의 날짜별 추이."""
    print(f"\n{'날짜':<12} {'시그널':<12} {'스코어':>8} {'현재가':>12} {'변동':>8}")
    print(f"{'-'*55}")

    prev_price = None
    for path in record_paths:
        record = load_record(path)
        for s in record["stocks"]:
            if s["ticker"] == ticker or s["name"] == ticker:
                price = s["current_price"]
                if prev_price and prev_price > 0:
                    change = ((price - prev_price) / prev_price) * 100
                    change_str = f"{change:+.1f}%"
                else:
                    change_str = "-"
                print(f"{record['date']:<12} {s['signal']:<12} {s['weighted_score']:>8.3f} {price:>12,.0f} {change_str:>8}")
                prev_price = price
                break


def _show_all_history(record_paths: list[Path]) -> None:
    """전체 종목 날짜별 시그널 변화 매트릭스."""
    # 모든 종목 수집
    all_stocks = {}
    for path in record_paths:
        record = load_record(path)
        for s in record["stocks"]:
            all_stocks[s["ticker"]] = s["name"]

    # 헤더
    dates = [p.stem for p in record_paths]
    header = f"{'종목':<12}" + "".join(f"{d[-5:]:>10}" for d in dates)
    print(f"\n{header}")
    print("-" * (12 + len(dates) * 10))

    # 각 종목별 시그널 추이
    for ticker, name in sorted(all_stocks.items(), key=lambda x: x[1]):
        row = f"{name:<12}"
        for path in record_paths:
            record = load_record(path)
            found = False
            for s in record["stocks"]:
                if s["ticker"] == ticker:
                    sig = s["signal"]
                    score = s["weighted_score"]
                    row += f"{sig[:4]:>6}{score:.2f}"
                    found = True
                    break
            if not found:
                row += f"{'--':>10}"
        print(row)


def compare_days(day1: str, day2: str) -> None:
    """두 날짜 기록 비교."""
    path1 = HISTORY_DIR / f"{day1}.json"
    path2 = HISTORY_DIR / f"{day2}.json"

    if not path1.exists() or not path2.exists():
        print(f"기록 파일이 없습니다: {path1 if not path1.exists() else path2}")
        return

    r1 = load_record(path1)
    r2 = load_record(path2)

    map1 = {s["ticker"]: s for s in r1["stocks"]}
    map2 = {s["ticker"]: s for s in r2["stocks"]}

    print(f"\n비교: {day1} vs {day2}")
    print(f"{'='*70}")
    print(f"{'종목':<12} {day1[-5:]+' 시그널':>14} {day2[-5:]+' 시그널':>14} {'스코어 변화':>12} {'가격 변화':>12}")
    print(f"{'-'*70}")

    for ticker in map2:
        s1 = map1.get(ticker)
        s2 = map2[ticker]
        if not s1:
            continue

        score_diff = s2["weighted_score"] - s1["weighted_score"]
        if s1["current_price"] > 0:
            price_change = ((s2["current_price"] - s1["current_price"]) / s1["current_price"]) * 100
            price_str = f"{price_change:+.1f}%"
        else:
            price_str = "-"

        signal_marker = " **" if s1["signal"] != s2["signal"] else ""
        print(f"{s2['name']:<12} {s1['signal']:>14} {s2['signal']:>14} {score_diff:>+12.3f} {price_str:>12}{signal_marker}")

    print(f"{'='*70}")
    print("** = 시그널 변경")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="History Viewer")
    parser.add_argument("command", choices=["latest", "history", "compare"], help="조회 명령")
    parser.add_argument("--ticker", help="특정 종목 필터")
    parser.add_argument("--days", type=int, default=7, help="조회 일수")
    parser.add_argument("--day1", help="비교 날짜1 (YYYY-MM-DD)")
    parser.add_argument("--day2", help="비교 날짜2 (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.command == "latest":
        show_latest()
    elif args.command == "history":
        show_history(args.ticker, args.days)
    elif args.command == "compare":
        if args.day1 and args.day2:
            compare_days(args.day1, args.day2)
        else:
            print("--day1, --day2 필요")
