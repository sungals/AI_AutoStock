"""기업 마스터 구축 — pykrx 종목 리스트 + (선택) DART corp_code 매핑.

DART 키가 있으면 corp_code를 매핑(재무 수집의 키)하고, 없으면 'X'+종목코드를
임시 키로 사용해 가격 수집만으로도 동작하게 한다.
05-구현-가이드.md §2.1. Python 3.9 호환.
"""
from typing import List, Dict, Optional, Callable
import io
import zipfile
import xml.etree.ElementTree as ET
import requests
import config


def fetch_dart_corp_map(api_key: str) -> Dict[str, Dict]:
    """DART corpCode.xml → {stock_code: {corp_code, corp_name}} (상장사만)."""
    resp = requests.get(config.DART_CORPCODE_URL, params={'crtfc_key': api_key},
                        timeout=30)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        xml_content = z.read('CORPCODE.xml')
    root = ET.fromstring(xml_content)
    out = {}  # type: Dict[str, Dict]
    for item in root.findall('list'):
        code = (item.findtext('stock_code') or '').strip()
        if code:  # 상장사만 (비상장은 stock_code 공란)
            out[code] = {
                'corp_code': (item.findtext('corp_code') or '').strip(),
                'corp_name': (item.findtext('corp_name') or '').strip(),
            }
    return out


def upsert_companies(conn, rows: List[Dict]) -> int:
    """companies 멱등 저장. rows: dict(corp_code, stock_code, corp_name, market)."""
    n = 0
    for r in rows:
        conn.execute(
            """INSERT OR REPLACE INTO companies
               (corp_code, stock_code, corp_name, market) VALUES (?,?,?,?)""",
            (r['corp_code'], r['stock_code'], r['corp_name'], r.get('market', 'KOSPI')))
        n += 1
    return n


def build_company_master(conn, markets=('KOSPI', 'KOSDAQ'),
                         api_key: Optional[str] = None,
                         ticker_fn: Optional[Callable] = None,
                         name_fn: Optional[Callable] = None,
                         corp_map_fn: Optional[Callable] = None) -> int:
    """종목 마스터 구축. fetch 함수 주입 시 네트워크 없이 테스트 가능."""
    if api_key is None:
        api_key = config.OPENDART_API_KEY

    if ticker_fn is None:
        from pykrx import stock
        ticker_fn = lambda m: stock.get_market_ticker_list(market=m)
    if name_fn is None:
        from pykrx import stock
        name_fn = stock.get_market_ticker_name

    corp_map = {}  # type: Dict[str, Dict]
    if api_key:
        corp_map = (corp_map_fn or fetch_dart_corp_map)(api_key)

    rows = []  # type: List[Dict]
    for market in markets:
        for ticker in ticker_fn(market):
            info = corp_map.get(ticker)
            corp_code = info['corp_code'] if info else ('X' + ticker)  # 폴백 키
            corp_name = (info['corp_name'] if info else None) or name_fn(ticker)
            rows.append({'corp_code': corp_code, 'stock_code': ticker,
                         'corp_name': corp_name, 'market': market})
    return upsert_companies(conn, rows)
