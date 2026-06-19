# Codex 체크포인트 ① — config · 마이그레이션 · Point-in-Time (Task 1~3)

> cold-start라면 먼저 `00-codex-시작가이드.md`를 읽으세요. 이 문서는 Task 1~3의 상세 가이드입니다.
> 목표: **미래참조 편향(look-ahead bias) 차단의 토대**를 만든다.

---

## 이 구간이 푸는 문제

기존 백테스트는 재무제표를 `bsns_year`(사업연도)로만 조회한다. 그런데 2024년 사업보고서는
실제로 **2025년 3월경에야 공시**된다. 과거 2025-02-01 시점 백테스트가 이 데이터를 쓰면,
"미래에 알게 될 정보로 과거에 매매"하는 미래참조 편향이다. → `disclosed_at`(공시일)을 부여하고
백테스트 시점 `T`에서 `disclosed_at <= T`만 쓰도록 게이팅한다.

---

## Task 1 — config 설정

`config.py`에 아래를 추가하고 `tests/test_config_reliability.py`로 검증. (상세 코드: `01-구현-플랜.md` Task 1)
핵심 상수: `COMMISSION_RATE, SLIPPAGE_BPS, PIT_ANNUAL_LAG_DAYS(=90), PIT_QUARTER_LAG_DAYS(=45),
PRICE_LIMIT_PCT(=0.30), MIN_TRADE_VALUE_KRW, OOS_FRACTION(=0.30), MIN_DEFLATED_SR(=0.95),
SELL_TAX_TABLE, TICK_TABLE`. 정확한 값은 스펙 `00-스펙-설계.md §6`.

## Task 2 — 스키마 마이그레이션

멱등 함수 `_migrate_add_reliability_columns(conn)`를 추가하고 `init_db()`에서 호출.
추가 컬럼:
- `financial_statements.disclosed_at TEXT`
- `simulation_runs.{is_cagr, oos_cagr, deflated_sharpe, cost_bps, gate_passed, gate_reason}`
- `backtest_runs.{slippage_bps, tax_rate, fill_model}`

검증: `tests/test_migrations_reliability.py` — 컬럼 존재 + `init_db()` 두 번 호출해도 무에러(멱등).

## Task 3 — point_in_time.py (핵심)

**API**
```python
estimate_disclosed_at(bsns_year: str, reprt_code: str) -> str   # 공시일 추정(lag fallback)
get_financials_asof(conn, corp_code: str, as_of_date: str) -> List[Dict]  # disclosed_at<=T만
get_metrics_asof(conn, corp_code: str, as_of_date: str) -> Dict[str, float]  # PIT 재무로 재계산
```

**보고서 코드 → 결산 기준일**
| reprt_code | 의미 | 기준일 | lag |
|-----------|------|--------|-----|
| 11011 | 사업보고서(연간) | 12-31 | ANNUAL(90) |
| 11013 | 1분기 | 03-31 | QUARTER(45) |
| 11012 | 반기 | 06-30 | QUARTER(45) |
| 11014 | 3분기 | 09-30 | QUARTER(45) |

**가장 중요한 테스트 (반드시 통과)** — 미래참조 누수 차단:
```python
# 2024 사업보고서가 2025-03-15 공시 → 2025-02-01엔 안 보이고 2025-04-01엔 보여야
rows = pit.get_financials_asof(conn, '00126380', '2025-02-01'); assert rows == []
rows = pit.get_financials_asof(conn, '00126380', '2025-04-01'); assert len(rows) == 1
```

**`disclosed_at` 채우는 법(우선순위)**
1. `dart_disclosures.rcept_dt`를 `(corp_code, bsns_year, reprt_code)`로 매칭 (정확)
   — `rcept_dt`는 'YYYYMMDD' 형식이므로 'YYYY-MM-DD'로 변환.
2. 매칭 실패 시 `estimate_disclosed_at()` lag fallback.

**구현 코드 전체**: `01-구현-플랜.md` Task 3 Step 3 참조.

---

## 함정

- `get_metrics_asof`는 `calculated_metrics` 테이블을 직접 읽으면 **안 됨**(그 안에 미래 데이터가 섞임).
  반드시 `get_financials_asof`로 가져온 재무 + `as_of` 시점 시세로 `metrics_calculator.calc_*`를 다시 호출.
- `disclosed_at`이 NULL인 기존 데이터가 많을 것 → fallback이 항상 동작하도록.

## 이 구간 완료 신호

```bash
python -m pytest tests/test_config_reliability.py tests/test_migrations_reliability.py tests/test_point_in_time.py -v
# 모두 PASS면 → 02-codex-execution-model.md 로 진행
```
