"""재무제표 수집 (DART OpenAPI) → financial_statements 테이블.

핵심: 실제 공시일(rcept_dt)을 disclosed_at에 채워 PIT 게이트를 '추정'이 아닌 '실측'으로
만든다. CFS(연결) 우선 → OFS(개별) 폴백. DART 키 없으면 graceful skip.
02-외부-API-가이드.md §1, 03-시스템-아키텍처.md. Python 3.9 호환.
"""
from typing import List, Dict, Optional, Callable, Tuple
import requests
import config
import point_in_time
from rate_limit import rate_limited


def _to_int(raw) -> Optional[int]:
    """DART 금액 문자열('1,234' / '-' / '')을 int로. 실패 시 None."""
    if raw is None:
        return None
    s = str(raw).replace(',', '').strip()
    if s in ('', '-'):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _dart_get(path: str, params: Dict) -> Dict:
    resp = requests.get('%s/%s' % (config.DART_BASE, path), params=params, timeout=20)
    return resp.json()


@rate_limited(config.DART_DELAY)
def fetch_financials(api_key: str, corp_code: str, bsns_year: str,
                     reprt_code: str, fs_div: str) -> Optional[List[Dict]]:
    """단일회사 전체 재무제표 (fnlttSinglAcntAll.json). 없으면 None."""
    data = _dart_get('fnlttSinglAcntAll.json', {
        'crtfc_key': api_key, 'corp_code': corp_code,
        'bsns_year': bsns_year, 'reprt_code': reprt_code, 'fs_div': fs_div})
    if data.get('status') == '000':
        return data.get('list', [])
    return None


def fetch_financials_cfs_first(api_key: str, corp_code: str, bsns_year: str,
                               reprt_code: str,
                               fetch_fn: Optional[Callable] = None
                               ) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """CFS(연결) 우선 → OFS(개별) 폴백. 반환: (list, fs_div) 또는 (None, None)."""
    fetch = fetch_fn or fetch_financials
    for fs_div in ('CFS', 'OFS'):
        rows = fetch(api_key, corp_code, bsns_year, reprt_code, fs_div)
        if rows:
            return rows, fs_div
    return None, None


@rate_limited(config.DART_DELAY)
def fetch_disclosure_date(api_key: str, corp_code: str, bsns_year: str,
                          reprt_code: str) -> Optional[str]:
    """정기보고서 실제 공시일(rcept_dt) 조회 → 'YYYY-MM-DD'. 실패 시 None.

    list.json에서 보고서명 키워드가 일치하는 정기공시를 찾는다.
    """
    keyword = config.DART_REPRT_KEYWORD.get(reprt_code, u'사업보고서')
    year = int(bsns_year)
    data = _dart_get('list.json', {
        'crtfc_key': api_key, 'corp_code': corp_code,
        'bgn_de': '%d0101' % year, 'end_de': '%d1231' % (year + 1),
        'pblntf_ty': 'A', 'page_count': 100})
    if data.get('status') != '000':
        return None
    for item in data.get('list', []):
        if keyword in (item.get('report_nm') or ''):
            rcept = (item.get('rcept_dt') or '').strip()   # 'YYYYMMDD'
            if len(rcept) == 8 and rcept.isdigit():
                return '%s-%s-%s' % (rcept[:4], rcept[4:6], rcept[6:8])
    return None


def upsert_financials(conn, corp_code: str, bsns_year: str, reprt_code: str,
                      fs_div: str, items: List[Dict], disclosed_at: str) -> int:
    """재무 항목을 financial_statements에 멱등 저장 (disclosed_at 포함)."""
    n = 0
    for it in items:
        account_id = (it.get('account_id') or '').strip()
        if not account_id or account_id == '-':
            continue
        conn.execute(
            """INSERT OR REPLACE INTO financial_statements
               (corp_code, bsns_year, reprt_code, fs_div, sj_div, account_id,
                thstrm_amount, disclosed_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (corp_code, bsns_year, reprt_code, fs_div,
             (it.get('sj_div') or '').strip(), account_id,
             _to_int(it.get('thstrm_amount')), disclosed_at))
        n += 1
    return n


def collect_financials(conn, corp_codes: List[str], years: List[str],
                       reprt_codes=('11011',), api_key: Optional[str] = None,
                       fetch_fn: Optional[Callable] = None,
                       disclosure_fn: Optional[Callable] = None) -> Dict:
    """여러 기업·연도의 재무를 수집·저장. DART 키 없으면 skip.

    disclosed_at은 fetch_disclosure_date(rcept_dt) → 실패 시 PIT lag 추정으로 폴백.
    """
    if api_key is None:
        api_key = config.OPENDART_API_KEY
    if not api_key:
        return {'skipped': True, 'reason': 'OPENDART_API_KEY 없음', 'rows': 0}

    disc_fn = disclosure_fn or fetch_disclosure_date
    result = {'skipped': False, 'companies': 0, 'rows': 0, 'no_data': 0}
    for corp in corp_codes:
        got_any = False
        for year in years:
            for reprt in reprt_codes:
                items, fs_div = fetch_financials_cfs_first(
                    api_key, corp, year, reprt, fetch_fn=fetch_fn)
                if not items:
                    result['no_data'] += 1
                    continue
                disclosed = disc_fn(api_key, corp, year, reprt) or \
                    point_in_time.estimate_disclosed_at(year, reprt)
                result['rows'] += upsert_financials(
                    conn, corp, year, reprt, fs_div, items, disclosed)
                got_any = True
        if got_any:
            result['companies'] += 1
    return result


@rate_limited(config.DART_DELAY)
def fetch_total_shares(api_key: str, corp_code: str, bsns_year: str,
                       reprt_code: str = '11011') -> Optional[int]:
    """발행 보통주 총수 (stockTotqySttus.json). KRX 시총 차단 우회용.

    se(구분)가 '보통주'인 행의 istc_totqy(발행주식 총수)를 우선 사용,
    없으면 '합계' 행으로 폴백. 실패 시 None.
    """
    data = _dart_get('stockTotqySttus.json', {
        'crtfc_key': api_key, 'corp_code': corp_code,
        'bsns_year': bsns_year, 'reprt_code': reprt_code})
    if data.get('status') != '000':
        return None
    rows = data.get('list', [])
    for it in rows:
        if u'보통주' in (it.get('se') or ''):
            n = _to_int(it.get('istc_totqy'))
            if n:
                return n
    for it in rows:
        if u'합계' in (it.get('se') or ''):
            n = _to_int(it.get('istc_totqy'))
            if n:
                return n
    return None


def populate_market_cap(conn, years=('2024', '2023', '2022'),
                        api_key: Optional[str] = None,
                        shares_fn: Optional[Callable] = None,
                        refresh: bool = False) -> Dict:
    """DART 발행주식수 × 종가로 price_data.market_cap을 채운다.

    KRX 시총 엔드포인트(data.krx.co.kr)가 막혀 빈 응답을 줄 때의 우회 경로.
    실제 corp_code가 매핑된 종목만 대상. shares_fn 주입 시 네트워크 없이 테스트 가능.

    효율화(EOD 매일 실행용):
    - 발행주식수는 `companies.shares_outstanding`에 캐시 → DART 재호출 최소화.
    - market_cap이 비어있는 행만 갱신(refresh=True면 전체 재계산).
    - 갱신할 행도 없고 캐시도 있으면 DART 호출 자체를 생략.

    Returns: {updated, no_shares, rows, fetched}
    """
    if api_key is None:
        api_key = config.OPENDART_API_KEY
    if not api_key:
        return {'skipped': True, 'reason': 'OPENDART_API_KEY 없음', 'updated': 0}
    fetch = shares_fn or fetch_total_shares

    companies = conn.execute(
        "SELECT corp_code, stock_code, shares_outstanding FROM companies "
        "WHERE corp_code NOT LIKE 'X%'").fetchall()
    result = {'skipped': False, 'updated': 0, 'no_shares': 0, 'rows': 0, 'fetched': 0}
    for c in companies:
        # 갱신 대상 행 존재 여부 (refresh면 전체, 아니면 market_cap NULL인 행만)
        if refresh:
            need = conn.execute(
                "SELECT COUNT(*) n FROM price_data WHERE stock_code=?",
                (c['stock_code'],)).fetchone()['n']
        else:
            need = conn.execute(
                "SELECT COUNT(*) n FROM price_data "
                "WHERE stock_code=? AND market_cap IS NULL",
                (c['stock_code'],)).fetchone()['n']
        if not need:
            continue

        shares = c['shares_outstanding']
        if shares is None or refresh:
            shares = None
            for y in years:
                shares = fetch(api_key, c['corp_code'], y)
                if shares:
                    break
            result['fetched'] += 1
            if shares:
                conn.execute(
                    "UPDATE companies SET shares_outstanding=? WHERE corp_code=?",
                    (shares, c['corp_code']))
        if not shares:
            result['no_shares'] += 1
            continue

        if refresh:
            cur = conn.execute(
                "UPDATE price_data SET market_cap = close * ? WHERE stock_code = ?",
                (shares, c['stock_code']))
        else:
            cur = conn.execute(
                "UPDATE price_data SET market_cap = close * ? "
                "WHERE stock_code = ? AND market_cap IS NULL",
                (shares, c['stock_code']))
        result['rows'] += cur.rowcount
        result['updated'] += 1
    return result
