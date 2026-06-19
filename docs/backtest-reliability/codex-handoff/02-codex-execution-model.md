# Codex 체크포인트 ② — Execution Model (Task 4~5)

> cold-start라면 `00-codex-시작가이드.md` → `01-codex-point-in-time.md` 순으로 먼저.
> 목표: **체결 비현실성 제거** — 거래비용과 체결 가능성을 순수함수로 모델링.

---

## 이 구간이 푸는 문제

기존 백테스트는 `commission_rate`만 반영하고 **증권거래세(매도세)·슬리피지·상한가 매수불가·
거래정지·유동성·호가단위**를 무시한다. 그래서 현실에서 체결 불가능한 수익을 계상한다.
`execution_model.py`는 **DB 접근 없는 순수함수 모듈**(기존 `portfolio_operations.py`와 동일 스타일)이다.

---

## Task 4 — 비용 모델

**API**
```python
sell_tax_rate(trade_date: str) -> float
apply_costs(side, price, qty, trade_date, commission_rate, slippage_bps) -> Dict
# 반환 키: fill_price, gross, commission, tax, slippage, net
```

**규칙**
- 매수: 실지불 `net = gross + commission` (세금 없음)
- 매도: 실수령 `net = gross - commission - tax`, `tax = gross * sell_tax_rate(date)`
- 슬리피지: 매수는 불리하게 +, 매도는 -. `slip = price * slippage_bps/10000`
- 세율은 **시점 함수** — 과거 구간은 그 시점 세율. (2025:0.15% / 2024:0.18% / 2023:0.20% / 이전:0.23%)

**테스트**: `tests/test_execution_costs.py` — 매도 세금 포함, 매수 세금 0, 시점별 세율.

## Task 5 — 체결 가능성 · 호가단위

**API**
```python
round_to_tick(price: float) -> int           # 한국 호가단위 반올림
is_tradable(side, ohlcv: Dict, prev_close: int, min_value_krw=None) -> bool
```

**`is_tradable` False 조건**
- `volume == 0` (거래정지/거래없음)
- 매수 + 점상한가(`high==low` & `close>=상한가`) → 매수 불가
- 매도 + 점하한가(`high==low` & `close<=하한가`) → 매도 불가
- 당일 거래대금 < `MIN_TRADE_VALUE_KRW` (유동성 부족)
- 상·하한가 = `prev_close * (1 ± PRICE_LIMIT_PCT)`, `PRICE_LIMIT_PCT=0.30`

**호가단위 표(2023.1 개편, `config.TICK_TABLE`)**: 2천 미만 1원 / 5천 미만 5원 / 2만 미만 10원 /
5만 미만 50원 / 20만 미만 100원 / 50만 미만 500원 / 그 이상 1,000원.

**테스트**: `tests/test_execution_tradability.py` — 호가 반올림, 거래정지, 상한가 매수불가.

**구현 코드 전체**: `01-구현-플랜.md` Task 4~5 Step 3.

---

## 함정

- 순수함수 유지 — 이 모듈에서 `db`나 `conn`을 import하지 말 것.
- 상한가 판정은 `high==low`(점상한, 하루종일 잠김)일 때만 "체결불가"로. 장중 상한가 터치 후
  거래된 경우는 체결 가능으로 둔다(보수적 단순화).

## 이 구간 완료 신호

```bash
python -m pytest tests/test_execution_costs.py tests/test_execution_tradability.py -v
# PASS → 03-codex-validation-and-integration.md 로 진행
```
