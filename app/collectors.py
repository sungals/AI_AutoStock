"""수집 오케스트레이터 — 종목 마스터 → 가격(pykrx) → 재무(DART) 일괄 수집.

EOD 파이프라인의 데이터 수집 단계. 05-구현-가이드.md Phase 2,
03-시스템-아키텍처.md §6. Python 3.9 호환.
"""
from typing import List, Dict, Optional, Callable
import db_core
import company_master
import price_collector
import financial_collector


def collect_all(db_path: Optional[str], markets, start: str, end: str,
                years: List[str], stock_codes: Optional[List[str]] = None,
                build_master: bool = True,
                ticker_fn: Optional[Callable] = None,
                name_fn: Optional[Callable] = None) -> Dict:
    """전체 수집. start/end: 'YYYYMMDD'.

    - build_master=True: pykrx(+DART)로 종목 마스터 구축. False면 기존 companies 사용(증분).
    - stock_codes 지정 시 해당 종목만, 아니면 companies 전체.
    - DART 키 없으면 재무 수집 자동 skip(가격까지는 정상).
    """
    db_core.init_db(db_path)
    summary = {}  # type: Dict

    if build_master:
        with db_core.get_connection(db_path) as conn:
            summary['companies'] = company_master.build_company_master(
                conn, markets=markets, ticker_fn=ticker_fn, name_fn=name_fn)
    else:
        # 마스터 재구축 생략. 명시 종목이 companies에 없으면 최소 행 보장.
        if stock_codes:
            with db_core.get_connection(db_path) as conn:
                have = {r['stock_code'] for r in conn.execute(
                    "SELECT stock_code FROM companies").fetchall()}
                missing = [c for c in stock_codes if c not in have]
                if missing:
                    company_master.upsert_companies(conn, [
                        {'corp_code': 'X' + c, 'stock_code': c,
                         'corp_name': c, 'market': 'KOSPI'} for c in missing])
        summary['companies'] = 'reused'

    # 대상 종목/기업코드 확정
    with db_core.get_connection(db_path) as conn:
        if stock_codes is None:
            stock_codes = [r['stock_code'] for r in
                           conn.execute("SELECT stock_code FROM companies").fetchall()]
        corp_codes = []
        if stock_codes:
            placeholders = ','.join('?' * len(stock_codes))
            corp_codes = [r['corp_code'] for r in conn.execute(
                "SELECT corp_code FROM companies WHERE stock_code IN (%s)" % placeholders,
                stock_codes).fetchall()]

    with db_core.get_connection(db_path) as conn:
        summary['prices'] = price_collector.collect_prices(conn, stock_codes, start, end)

    with db_core.get_connection(db_path) as conn:
        summary['financials'] = financial_collector.collect_financials(
            conn, corp_codes, years)

    return summary
