"""대표 종목 워치리스트를 DB에 채우는 보조 CLI."""

import sys

import company_master
import config
import db_core
import financial_collector
import price_collector
from pykrx import stock
import watchlist


def _default_dates(conn):
    row = conn.execute("SELECT MIN(trade_date) AS a, MAX(trade_date) AS b FROM price_data").fetchone()
    start = (row['a'] or '2024-01-02').replace('-', '')
    end = (row['b'] or '2026-06-19').replace('-', '')
    years = sorted({start[:4], end[:4]})
    return start, end, years


def bootstrap(db_path=None):
    db_core.init_db(db_path)
    with db_core.get_connection(db_path) as conn:
        start, end, years = _default_dates(conn)
        corp_map = {}
        if config.OPENDART_API_KEY:
            corp_map = company_master.fetch_dart_corp_map(config.OPENDART_API_KEY)
        rows = []
        for market, codes in watchlist.REPRESENTATIVE_STOCKS.items():
            for code in codes:
                info = corp_map.get(code, {})
                rows.append({
                    'corp_code': info.get('corp_code') or ('X' + code),
                    'stock_code': code,
                    'corp_name': info.get('corp_name') or stock.get_market_ticker_name(code),
                    'market': market,
                })
        company_master.upsert_companies(conn, rows)
        summary_prices = price_collector.collect_prices(conn, [r['stock_code'] for r in rows], start, end)
        summary_financials = financial_collector.collect_financials(
            conn, [r['corp_code'] for r in rows], years)
    return {'prices': summary_prices, 'financials': summary_financials}


def main(argv=None):
    db_path = config.DB_PATH
    result = bootstrap(db_path)
    print(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
