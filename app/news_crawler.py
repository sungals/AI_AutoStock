"""뉴스 수집기 — Naver Search API → news_articles.

API 키가 없으면 안전하게 skip한다. 테스트와 운영 안정성을 위해 HTTP fetch 함수를 주입할 수 있다.
05-구현-가이드 Phase 5. Python 3.9 호환.
"""
from typing import Callable, Dict, List, Optional
from datetime import datetime
from email.utils import parsedate_to_datetime
import html
import re
import time

import requests

import config
import sentiment_analyzer


TAG_RE = re.compile(r'<[^>]+>')


def _strip_html(value: str) -> str:
    text = TAG_RE.sub('', value or '')
    return html.unescape(text).strip()


def _parse_pubdate(value: str) -> str:
    if not value:
        return ''
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        try:
            return datetime.fromisoformat(value).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return value[:19]


def parse_naver_article(item: Dict) -> Dict:
    """Naver Search API article item을 내부 news_articles 형식으로 변환."""
    return {
        'title': _strip_html(item.get('title', '')),
        'summary': _strip_html(item.get('description', '')),
        'url': item.get('originallink') or item.get('link') or '',
        'published_at': _parse_pubdate(item.get('pubDate', '')),
        'source': item.get('source', '') or '',
    }


def fetch_naver_news(query: str, display: int = 20, sort: str = 'date',
                     client_id: Optional[str] = None,
                     client_secret: Optional[str] = None) -> List[Dict]:
    """Naver Search API 원시 item 목록 조회."""
    cid = client_id if client_id is not None else config.NAVER_CLIENT_ID
    secret = client_secret if client_secret is not None else config.NAVER_CLIENT_SECRET
    headers = {
        'X-Naver-Client-Id': cid,
        'X-Naver-Client-Secret': secret,
    }
    resp = requests.get(
        config.NAVER_NEWS_URL, headers=headers,
        params={'query': query, 'display': display, 'sort': sort}, timeout=10)
    resp.raise_for_status()
    return resp.json().get('items', [])


def fetch_news_for_stock(conn, stock_code: str, corp_name: str,
                         client_id: Optional[str] = None,
                         client_secret: Optional[str] = None,
                         display: int = 20,
                         fetch_fn: Optional[Callable] = None) -> Dict:
    """단일 종목 뉴스 수집 및 저장."""
    cid = client_id if client_id is not None else config.NAVER_CLIENT_ID
    secret = client_secret if client_secret is not None else config.NAVER_CLIENT_SECRET
    if not cid or not secret:
        return {'skipped': True, 'reason': 'NAVER_CLIENT_ID/SECRET 없음', 'rows': 0}

    fetch = fetch_fn or (lambda query, display, sort:
                         fetch_naver_news(query, display, sort, cid, secret))
    items = fetch(corp_name, display, 'date')
    rows = 0
    for item in items:
        parsed = parse_naver_article(item)
        if not parsed['title']:
            continue
        sentiment_analyzer.upsert_news_article(
            conn, stock_code, parsed['title'], parsed['url'],
            parsed['published_at'], source=parsed['source'],
            summary=parsed['summary'])
        rows += 1
    return {'skipped': False, 'rows': rows}


def fetch_all_news(conn, display: int = 20,
                   fetch_fn: Optional[Callable] = None) -> Dict:
    """companies 전체 뉴스 수집."""
    rows = conn.execute(
        "SELECT stock_code, corp_name FROM companies ORDER BY stock_code").fetchall()
    result = {'skipped': False, 'companies': 0, 'rows': 0, 'errors': 0, 'error': ''}
    for r in rows:
        try:
            res = fetch_news_for_stock(
                conn, r['stock_code'], r['corp_name'], display=display, fetch_fn=fetch_fn)
        except Exception as e:
            result['errors'] += 1
            result['error'] = str(e)
            break
        if res.get('skipped'):
            return res
        result['companies'] += 1
        result['rows'] += res['rows']
        time.sleep(config.NAVER_DELAY)
    return result
