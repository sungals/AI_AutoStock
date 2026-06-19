"""대시보드 데이터 조회 헬퍼."""

from typing import Dict, List, Optional, Sequence


def _latest_rows(conn, table: str, key_col: str, order_col: str) -> Dict[str, dict]:
    rows = conn.execute(
        """
        SELECT *
          FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                     PARTITION BY {key_col}
                     ORDER BY {order_col} DESC, id DESC
                   ) AS rn
            FROM {table}
          )
         WHERE rn = 1
        """.format(table=table, key_col=key_col, order_col=order_col)
    ).fetchall()
    return {row[key_col]: dict(row) for row in rows}


def get_representative_overviews(conn, stock_codes: Sequence[str]) -> List[Dict]:
    if not stock_codes:
        return []
    latest_price = conn.execute(
        """
        SELECT *
          FROM (
            SELECT stock_code,
                   trade_date,
                   close,
                   market_cap,
                   LAG(close) OVER (
                     PARTITION BY stock_code
                     ORDER BY trade_date
                   ) AS prev_close,
                   ROW_NUMBER() OVER (
                     PARTITION BY stock_code
                     ORDER BY trade_date DESC, id DESC
                   ) AS rn
              FROM price_data
          )
         WHERE rn = 1
        """
    ).fetchall()
    latest_price = {row['stock_code']: dict(row) for row in latest_price}
    latest_screen = _latest_rows(conn, 'screening_results', 'stock_code', 'screen_date')
    latest_fusion = _latest_rows(conn, 'fusion_signals', 'stock_code', 'calc_date')
    rows = []
    for code in stock_codes:
        company = conn.execute(
            "SELECT corp_code, stock_code, corp_name, sector, market FROM companies WHERE stock_code=?",
            (code,)).fetchone()
        if not company:
            continue
        price = latest_price.get(code, {})
        screen = latest_screen.get(code, {})
        fusion = latest_fusion.get(code, {})
        close = price.get('close')
        prev_close = price.get('prev_close')
        change_pct = None
        if close is not None and prev_close not in (None, 0):
            change_pct = round((float(close) - float(prev_close)) * 100.0 / float(prev_close), 2)
        rows.append({
            'market': company['market'],
            'stock_code': company['stock_code'],
            'corp_name': company['corp_name'],
            'sector': company['sector'],
            'trade_date': price.get('trade_date'),
            'close': close,
            'change_pct': change_pct,
            'market_cap': price.get('market_cap'),
            'screen_strategy': screen.get('strategy'),
            'screen_score': screen.get('score'),
            'fusion_score': fusion.get('fusion_score'),
            'recommendation': fusion.get('recommendation'),
        })
    return rows
