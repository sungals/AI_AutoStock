# Codex 체크포인트 ③ — 통합 · 검증 · 생존편향 (Task 6~12)

> cold-start라면 `00-codex-시작가이드.md` → `01` → `02` 순으로 먼저.
> 목표: 앞서 만든 PIT 게이트·체결 모델을 엔진에 **통합**하고, **과최적화 방지**와
> **생존편향 경고**를 더해 신뢰성 레이어를 완성한다.

---

## Task 6 — backtester 통합 (PIT + 비용)

`backtester.py`가 재무 조회를 `point_in_time.get_metrics_asof`로, 체결을
`execution_model.apply_costs`/`is_tradable`/`round_to_tick`로 경유하게 수정.
기존 동작은 `fill_model='ideal'`로 보존(비교용), 신뢰성 경로는 `fill_model='realistic'`.

**가장 중요한 테스트 — 회귀 특성테스트**:
```python
def test_costs_reduce_reported_cagr(...):
    res_real = run_backtest(..., fill_model='realistic')
    res_free = run_backtest(..., fill_model='ideal')
    assert res_real['cagr'] <= res_free['cagr']   # 신뢰성 적용 = 보수화
```
이 테스트가 통과하면 "신뢰성 레이어가 실제로 부풀린 수익을 깎고 있다"는 증거.

---

## Task 7 — validation_harness.py: IS/OOS 분리

```python
split_is_oos(window_start, window_end, oos_fraction=0.30)
  -> ((is_start, is_end), (oos_start, oos_end))
```
앞 70% = In-Sample(파라미터 학습), 뒤 30% = Out-of-Sample(성과 보고). 경계 연속(`is_end == oos_start`).

## Task 8 — validation_harness.py: Deflated Sharpe + 게이트

```python
deflated_sharpe_ratio(observed_sharpe, n_trials, n_obs, skew=0.0, kurt=3.0) -> float
passes_gate(is_metrics, oos_metrics, deflated_sr, min_dsr=0.95) -> (bool, reason)
```
**Deflated Sharpe Ratio (Bailey & López de Prado)**: n_trials개 전략을 시도하면 우연히 높은
Sharpe가 나오기 마련 → 그 기대 최대값을 차감해 "진짜인지" 확률(0~1)로 보정. n_trials↑ → DSR↓.

구현 개요(numpy 정규분포 CDF 사용):
```python
import numpy as np
from math import sqrt, log
def _expected_max_sharpe(n_trials):
    # E[max] ≈ (1-γ)·Z⁻¹(1-1/N) + γ·Z⁻¹(1-1/(N·e)), γ=0.5772(오일러)
    from scipy.stats import norm  # 또는 numpy 근사 inverse-CDF 직접 구현
    gamma = 0.5772156649
    return ((1-gamma)*norm.ppf(1-1.0/n_trials)
            + gamma*norm.ppf(1-1.0/(n_trials*np.e)))
```
> scipy가 환경에 없으면 `statsmodels`(이미 의존성)나 numpy로 inverse-CDF를 근사 구현하세요.
> 의존성 추가 금지 — `01-기술-스택.md`의 기존 목록(numpy, statsmodels) 내에서 해결.

**`passes_gate` 통과 조건(전부 충족)**:
- `oos_metrics['cagr'] > 0`
- `oos_metrics['sharpe'] >= is_metrics['sharpe'] * 0.5`
- `deflated_sr >= min_dsr`

## Task 9 — simulation_runner 통합

`_run_single_simulation`이: `split_is_oos`로 IS/OOS 백테스트 →
`deflated_sharpe_ratio(n_trials=len(param_list))` → `passes_gate` →
`simulation_runs`에 `is_cagr, oos_cagr, deflated_sharpe, gate_passed, gate_reason, cost_bps` 저장.

## Task 10 — algo_optimizer 게이팅

`apply_optimal_params`가 **`gate_passed=1`인 run만** 후보로 사용. 탈락 파라미터는 반영하지 않고
`gate_reason`을 로깅. (파이프라인 Step 7~8이 노이즈에 fitting되는 것을 차단)

## Task 11 — bias_report.py (생존편향)

```python
estimate_survivorship_bias(conn, start_date, end_date) -> Dict
  # {'delisted_ratio', 'estimated_cagr_haircut_pct', 'warning'}
apply_haircut(reported_cagr, haircut_pct) -> float
```
`price_data`에서 **마지막 거래일이 `end_date`보다 이른 종목**(중도 소멸 추정) 비율을 계산.
이 비율에 비례해 보수적 haircut. 이 모듈은 수익률을 **낮추는 방향으로만** 작동. 한계 명시:
"⚠️ 상장폐지 종목 미반영 — 실제 수익률은 더 낮을 수 있음".

## Task 12 — 리포트/대시보드 노출

일일 리포트(`claude_analyzer.py` 또는 리포트 생성기)와 해당 라우트에 생존편향 경고 +
OOS CAGR + Deflated Sharpe를 노출.

---

## 함정

- **n_trials 연결**: Task 9에서 `deflated_sharpe_ratio`에 넘기는 `n_trials`는 시뮬레이션이 실제로
  탐색한 파라미터 조합 수여야 함(`simulation_runner`의 `param_list` 길이). 1을 넘기면 보정이 무의미.
- **OOS 부족**: 윈도우가 짧아 OOS 구간이 비면 `gate_reason='insufficient_oos'`로 마킹하고 옵티마이저 제외.
- **기존 테스트 회귀**: `fill_model='ideal'` 경로가 기존 동작을 보존하는지 확인(레거시 테스트 통과 유지).

## 최종 완료 신호 (Definition of Done)

```bash
python -m pytest tests/ -q          # 신규+기존 전부 PASS, 회귀 없음
```
- 미래참조 누수 테스트 통과 (체크포인트 ①)
- 비용 적용 후 CAGR 하락 특성테스트 통과 (Task 6)
- `simulation_runs`에 oos/deflated/gate 컬럼 기록 (Task 9)
- 옵티마이저가 gate 미통과 파라미터 미반영 (Task 10)
- 리포트에 생존편향 경고 노출 (Task 12)

완료 시 `00-스펙-설계.md §10` 성공 기준 전부 충족.
