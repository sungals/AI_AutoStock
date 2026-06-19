"""테스트 공용 픽스처 — 합성 시세 DB 시드."""
from datetime import date, timedelta
import numpy as np
import pytest

import db_core


def _trading_dates(start, n):
    d = date.fromisoformat(start)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def seed_prices(dbp, n_days=320, seed=7):
    db_core.init_db(dbp)
    rng = np.random.default_rng(seed)
    dates = _trading_dates('2022-01-03', n_days)
    drifts = [0.0016, 0.0012, 0.0008, 0.0004, -0.0003, -0.0009, 0.0010, -0.0012]
    with db_core.get_connection(dbp) as conn:
        for i, drift in enumerate(drifts):
            code = '%06d' % (i + 1)
            conn.execute(
                "INSERT INTO companies (corp_code, stock_code, corp_name) VALUES (?,?,?)",
                ('C%06d' % i, code, 'CO%d' % i))
            price = 10000.0
            for dt in dates:
                price *= (1 + drift + rng.normal(0, 0.01))
                px = int(price)
                vol = 200000
                conn.execute(
                    """INSERT INTO price_data
                       (stock_code, trade_date, open, high, low, close, volume, market_cap, value)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (code, dt, px, int(px * 1.01), int(px * 0.99), px, vol,
                     px * 1_000_000, px * vol))
    return dates


@pytest.fixture
def seeded_db(tmp_path):
    dbp = str(tmp_path / 'q.db')
    dates = seed_prices(dbp)
    return dbp, dates


# ── 펀더멘털(가치·실적전환) 전략용 시드 ──

_NI = 'ifrs-full_ProfitLoss'
_EQ = 'ifrs-full_Equity'
_LB = 'ifrs-full_Liabilities'
_REV = 'ifrs-full_Revenue'
_OP = 'dart_OperatingIncomeLoss'

# 5개 종목: 시가총액(원) + 연도별 계정.  i=0..4 → stock '000001'..'000005'
#  000001(A): 저평가+우량(per5/pbr0.8/roe16/debt50)
#  000002(B): 저평가+우량(per8/pbr1.2/roe15/debt80)
#  000003(C): 고평가(per30/pbr5)              → value 탈락
#  000004(D): 흑자전환+매출급증               → turnaround 강함
#  000005(E): 평범(대조군)                    → 둘 다 탈락
_FUND = [
    dict(mcap=5_000_000_000, cur={_NI: 1_000_000_000, _EQ: 6_250_000_000,
         _LB: 3_125_000_000, _REV: 10_000_000_000, _OP: 1_200_000_000},
         prev={_REV: 9_500_000_000, _OP: 1_100_000_000, _NI: 900_000_000,
               _EQ: 6_000_000_000, _LB: 3_000_000_000}),
    dict(mcap=8_000_000_000, cur={_NI: 1_000_000_000, _EQ: 6_666_666_667,
         _LB: 5_333_333_333, _REV: 10_000_000_000, _OP: 1_100_000_000},
         prev={_REV: 9_800_000_000, _OP: 1_000_000_000, _NI: 900_000_000,
               _EQ: 6_400_000_000, _LB: 5_000_000_000}),
    dict(mcap=30_000_000_000, cur={_NI: 1_000_000_000, _EQ: 6_000_000_000,
         _LB: 12_000_000_000, _REV: 10_000_000_000, _OP: 1_000_000_000},
         prev={_REV: 9_900_000_000, _OP: 980_000_000, _NI: 980_000_000,
               _EQ: 5_900_000_000, _LB: 11_800_000_000}),
    dict(mcap=6_000_000_000, cur={_NI: 150_000_000, _EQ: 5_000_000_000,
         _LB: 6_000_000_000, _REV: 1_400_000_000, _OP: 200_000_000},
         prev={_REV: 1_000_000_000, _OP: -100_000_000, _NI: -80_000_000,
               _EQ: 5_000_000_000, _LB: 6_000_000_000}),
    dict(mcap=4_000_000_000, cur={_NI: 160_000_000, _EQ: 4_000_000_000,
         _LB: 8_000_000_000, _REV: 2_000_000_000, _OP: 180_000_000},
         prev={_REV: 1_960_000_000, _OP: 170_000_000, _NI: 150_000_000,
               _EQ: 3_900_000_000, _LB: 7_900_000_000}),
]


def seed_fundamentals(dbp, n_days=120, seed=11):
    """가치·실적전환 전략 검증용: 가격 + 시가총액 + 연간 재무(2020/2021) 시드."""
    db_core.init_db(dbp)
    rng = np.random.default_rng(seed)
    dates = _trading_dates('2022-01-03', n_days)
    with db_core.get_connection(dbp) as conn:
        for i, spec in enumerate(_FUND):
            code = '%06d' % (i + 1)
            corp = 'C%06d' % i
            conn.execute(
                "INSERT INTO companies (corp_code, stock_code, corp_name) VALUES (?,?,?)",
                (corp, code, 'CO%d' % i))
            price = 10000.0
            for dt in dates:
                price *= (1 + 0.0005 + rng.normal(0, 0.008))
                px = int(price)
                vol = 200000
                conn.execute(
                    """INSERT INTO price_data
                       (stock_code, trade_date, open, high, low, close, volume, market_cap, value)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (code, dt, px, int(px * 1.01), int(px * 0.99), px, vol,
                     spec['mcap'], px * vol))
            # 연간 재무 (둘 다 가격 구간 시작 전 공시 → 전 구간 가시)
            for year, accounts, disclosed in (
                    ('2020', spec['prev'], '2021-04-01'),
                    ('2021', spec['cur'], '2021-12-01')):
                for acc_id, amount in accounts.items():
                    conn.execute(
                        """INSERT INTO financial_statements
                           (corp_code, bsns_year, reprt_code, fs_div, sj_div,
                            account_id, thstrm_amount, disclosed_at)
                           VALUES (?,?, '11011', 'CFS', '', ?, ?, ?)""",
                        (corp, year, acc_id, amount, disclosed))
    return dates


@pytest.fixture
def fundamentals_db(tmp_path):
    dbp = str(tmp_path / 'qf.db')
    dates = seed_fundamentals(dbp)
    return dbp, dates
