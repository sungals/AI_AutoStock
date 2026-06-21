"""Point-in-Time 데이터 게이트 — 미래참조(look-ahead) 편향 차단.

특정 시점 T에 "그때 실제로 알 수 있었던" 재무 데이터만 반환한다.
docs/backtest-reliability/00-스펙-설계.md §4.1. Python 3.9 호환.
"""
from typing import Optional, List, Dict
from datetime import date, timedelta
import config

# DART 보고서 코드 → (결산 기준 월, 일)
_REPRT_PERIOD_END = {
    '11013': (3, 31),    # 1분기
    '11012': (6, 30),    # 반기
    '11014': (9, 30),    # 3분기
    '11011': (12, 31),   # 사업보고서(연간)
}


def estimate_disclosed_at(bsns_year: str, reprt_code: str) -> str:
    """공시일 미상 시 보수적 추정(공시 지연 lag 적용).

    - 사업보고서(11011): 회계연도 말 + PIT_ANNUAL_LAG_DAYS
    - 분기/반기(11013/11012/11014): 분기 말 + PIT_QUARTER_LAG_DAYS

    Returns:
        'YYYY-MM-DD'
    """
    year = int(bsns_year)
    month, day = _REPRT_PERIOD_END.get(reprt_code, (12, 31))
    base = date(year, month, day)
    if reprt_code == '11011':
        lag = config.PIT_ANNUAL_LAG_DAYS
    else:
        lag = config.PIT_QUARTER_LAG_DAYS
    return (base + timedelta(days=lag)).isoformat()


def _resolve_disclosed_at(row: Dict) -> str:
    """행의 disclosed_at을 확정. 비어있으면 lag fallback 추정."""
    disclosed = row.get('disclosed_at')
    if disclosed:
        # 'YYYYMMDD' 형식이면 'YYYY-MM-DD'로 정규화
        if len(disclosed) == 8 and disclosed.isdigit():
            return '%s-%s-%s' % (disclosed[:4], disclosed[4:6], disclosed[6:8])
        return disclosed
    return estimate_disclosed_at(row['bsns_year'], row['reprt_code'])


def get_financials_asof(conn, corp_code: str, as_of_date: str) -> List[Dict]:
    """as_of_date(포함) 시점까지 공시된 재무제표만 반환.

    불변식: 반환된 모든 행의 disclosed_at <= as_of_date.
    disclosed_at이 NULL이면 estimate_disclosed_at()로 보수적 추정.
    """
    rows = conn.execute(
        "SELECT * FROM financial_statements WHERE corp_code = ?", (corp_code,)
    ).fetchall()
    out = []  # type: List[Dict]
    for r in rows:
        d = dict(r)
        disclosed = _resolve_disclosed_at(d)
        if disclosed <= as_of_date:
            d['disclosed_at'] = disclosed
            out.append(d)
    return out


def _market_cap_asof(conn, stock_code: str, as_of_date: str) -> Optional[int]:
    """as_of 시점(포함) 이전 가장 최근 거래일의 시가총액. 미래참조 없음."""
    try:
        row = conn.execute(
            """SELECT market_cap FROM price_data
               WHERE stock_code = ? AND trade_date <= ?
               ORDER BY trade_date DESC LIMIT 1""",
            (stock_code, as_of_date),
        ).fetchone()
    except Exception:
        return None
    if row and row['market_cap']:
        return int(row['market_cap'])
    return None


def _pick_account(accmap, account_id, prefer_sj):
    """(account_id, sj_div) 맵에서 선호 재무제표(sj_div) 순으로 값을 고른다.

    선호 sj_div를 못 찾으면 해당 account_id의 아무 sj_div나 폴백(빈 sj_div 포함).
    """
    for sj in prefer_sj:
        if (account_id, sj) in accmap:
            return accmap[(account_id, sj)]
    for (aid, _sj), amount in accmap.items():
        if aid == account_id:
            return amount
    return None


# IFRS 계정 ID (자주 쓰는 것들)
_ACC_REVENUE = 'ifrs-full_Revenue'
_ACC_OPINCOME = 'dart_OperatingIncomeLoss'
_ACC_NETINCOME = 'ifrs-full_ProfitLoss'
_ACC_EQUITY = 'ifrs-full_Equity'
_ACC_LIABILITIES = 'ifrs-full_Liabilities'


def get_metrics_asof(conn, corp_code: str, as_of_date: str,
                     stock_code: Optional[str] = None) -> Dict[str, float]:
    """as_of 재무 + as_of 시점 시세로 가치·실적전환 지표를 재계산.

    핵심: calculated_metrics 테이블을 그대로 읽지 않는다(미래 데이터 혼입 위험).
    PIT 재무(get_financials_asof)에서 연간(11011) 데이터를 연도별로 모아
    당기/전기를 비교한다.

    반환 키: per, pbr, roe, debt_ratio, opm, revenue_growth_yoy, opincome_turnaround
    """
    import metrics_calculator as mc

    fins = get_financials_asof(conn, corp_code, as_of_date)
    if not fins:
        return {}

    # 연간(사업보고서) 데이터를 연도별 (계정, 재무제표구분) 맵으로 저장.
    # 같은 account_id가 BS/IS/CIS/CF/SCE에 중복 등장하므로 sj_div까지 키에 포함해
    # 올바른 재무제표에서 값을 골라야 한다(예: 자본총계는 BS, SCE의 부분값 아님).
    annual = {}  # type: Dict[str, Dict[Tuple[str, str], int]]
    for f in fins:
        if f.get('reprt_code') == '11011' and f.get('thstrm_amount') is not None:
            key = (f['account_id'], (f.get('sj_div') or ''))
            annual.setdefault(f['bsns_year'], {})[key] = f['thstrm_amount']
    if not annual:
        return {}

    years = sorted(annual.keys(), reverse=True)
    cur = annual[years[0]]
    prev = annual[years[1]] if len(years) > 1 else {}

    # 재무상태표(BS): 자본·부채·자산 / 손익계산서(IS,CIS): 매출·이익 (SCE/CF 중복값 배제)
    net_income = _pick_account(cur, _ACC_NETINCOME, ('IS', 'CIS', 'CF'))
    equity = _pick_account(cur, _ACC_EQUITY, ('BS',))
    liabilities = _pick_account(cur, _ACC_LIABILITIES, ('BS',))
    revenue = _pick_account(cur, _ACC_REVENUE, ('IS', 'CIS'))
    op = _pick_account(cur, _ACC_OPINCOME, ('IS', 'CIS'))

    out = {}  # type: Dict[str, float]

    roe = mc.calc_roe(net_income, equity)
    if roe is not None:
        out['roe'] = roe
    dr = mc.calc_debt_ratio(liabilities, equity)
    if dr is not None:
        out['debt_ratio'] = dr

    market_cap = _market_cap_asof(conn, stock_code, as_of_date) if stock_code else None
    if market_cap is not None:
        per = mc.calc_per(market_cap, net_income)
        if per is not None:
            out['per'] = per
        pbr = mc.calc_pbr(market_cap, equity)
        if pbr is not None:
            out['pbr'] = pbr

    # 영업이익률
    if revenue and revenue > 0 and op is not None:
        out['opm'] = round(op / revenue * 100, 2)

    # 매출 성장률 (전년 대비)
    rev_prev = _pick_account(prev, _ACC_REVENUE, ('IS', 'CIS'))
    if revenue is not None and rev_prev and rev_prev > 0:
        out['revenue_growth_yoy'] = round((revenue - rev_prev) / rev_prev * 100, 2)

    # 영업이익 흑자전환 (전년 적자/0 → 당기 흑자)
    op_prev = _pick_account(prev, _ACC_OPINCOME, ('IS', 'CIS'))
    if op is not None and op_prev is not None:
        out['opincome_turnaround'] = 1 if (op_prev <= 0 and op > 0) else 0

    return out
