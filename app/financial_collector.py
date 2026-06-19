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
