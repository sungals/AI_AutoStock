# Codex 시작 가이드 (Cold-Start 부트스트랩)

> **당신은 이 작업을 처음 보는 Codex(또는 다른) 에이전트입니다.** 이전 대화 맥락이 없다고 가정합니다.
> 이 문서 하나만 읽고도 작업을 이어받을 수 있도록 작성되었습니다. 침착하게 순서대로 읽으세요.

---

## 0. 한 문단 요약

`AI_AutoStock` 폴더는 **TTAK Quant**라는 한국 주식(KOSPI/KOSDAQ) 퀀트 + 자동매매
플랫폼의 설계 문서 패키지입니다(`00-프로젝트-개요.md` ~ `07-ENV-설정-템플릿.md`).
지금 진행 중인 작업은 그중 **백테스트 엔진의 신뢰성을 높이는 "백테스트 신뢰성 레이어"**
구현입니다. 백테스트가 수익률을 과대평가하는 4대 편향(생존편향·미래참조·체결비현실성·과최적화)을
점진적으로 보정합니다.

---

## 1. 먼저 읽어야 할 문서 (순서대로)

1. `docs/backtest-reliability/00-스펙-설계.md` — **무엇을/왜** 만드는지 (설계 명세)
2. `docs/backtest-reliability/01-구현-플랜.md` — **어떻게** 만드는지 (Task 1~12, TDD)
3. (참고) 루트의 `01-기술-스택.md`, `03-시스템-아키텍처.md`, `04-DB-스키마.md` — 기존 시스템 관례

---

## 2. 작업 환경 / 제약 (반드시 준수)

- **언어/런타임**: Python **3.9** (타입힌트는 `from typing import Optional` 사용. `int | None` 같은 3.10 문법 **금지**)
- **DB**: SQLite3, WAL 모드. DB 함수는 `conn`을 **외부에서 주입**받음(Connection Injection). 순수함수 모듈은 DB 접근 금지.
- **마이그레이션**: `PRAGMA table_info`로 컬럼 존재 확인 후 `ALTER TABLE` (멱등). `init_db()`에서 호출.
- **SQL**: 값은 항상 파라미터 바인딩(`?`). f-string으로 쿼리 생성 금지. (식별자=테이블/컬럼명은 코드 상수만 허용)
- **테스트**: `pytest`. 테스트는 `tests/`에 둠. **TDD 엄수** — 실패테스트 먼저 작성 → 실패 확인 → 최소 구현 → 통과 확인 → 커밋.
- **설정**: 매직넘버 금지. `config.py`에서 읽음 (Task 1에서 추가됨).
- **문서 언어**: 한국어 본문 + 영어 식별자.

> ⚠️ 이 폴더는 현재 **git 저장소가 아닐 수 있습니다.** 커밋 단계가 막히면 `git init` 후 진행하거나,
> 커밋을 건너뛰되 각 Task 완료 시점을 명확히 기록하세요. (실제 소스 코드 디렉토리 위치는
> `02-외부-API-가이드`/`05-구현-가이드`의 구조 — `app/` 또는 `ttak_quant/` 루트 — 를 따르세요.
> 신규 `.py` 모듈은 기존 `backtester.py`, `simulation_runner.py`와 같은 디렉토리에 둡니다.)

---

## 3. 만들/수정할 파일 한눈에

| 종류 | 파일 | Task |
|------|------|------|
| 수정 | `config.py` | 1 |
| 수정 | `db_core.py`/`db_financial.py`/`db_simulation.py` (마이그레이션) | 2 |
| **신규** | `point_in_time.py` | 3 |
| **신규** | `execution_model.py` | 4, 5 |
| 수정 | `backtester.py` | 6 |
| **신규** | `validation_harness.py` | 7, 8 |
| 수정 | `simulation_runner.py` | 9 |
| 수정 | `algo_optimizer.py` | 10 |
| **신규** | `bias_report.py` | 11 |
| 수정 | 리포트/라우트 | 12 |

---

## 4. 재개(Resume) 프로토콜 — "어디서부터 이어야 하나?"

1. **진행 상태 파악**: `tests/` 디렉토리에서 어떤 테스트 파일이 이미 존재하고 통과하는지 확인하세요.
   ```bash
   ls tests/ | grep -E "reliability|point_in_time|execution|validation|bias"
   python -m pytest tests/ -k "reliability or point_in_time or execution or validation or bias" -q
   ```
2. **신규 모듈 존재 확인**: `point_in_time.py`, `execution_model.py`, `validation_harness.py`, `bias_report.py` 중 무엇이 이미 있는지.
3. **다음 Task 결정**: `01-구현-플랜.md`의 의존성 순서(T1→T12)에서, **아직 테스트가 없거나 실패하는 가장 앞선 Task**부터 재개.
4. **체크포인트 문서 참조**: 해당 구간의 상세 가이드를 읽으세요.
   - Task 1~3 → `01-codex-point-in-time.md`
   - Task 4~5 → `02-codex-execution-model.md`
   - Task 6~12 → `03-codex-validation-and-integration.md`
5. **TDD로 진행**: 절대 구현부터 쓰지 말 것. 실패 테스트 → 구현 순서.

---

## 5. 완료 판정 (Definition of Done)

- 미래참조 누수 테스트 통과(`tests/test_point_in_time.py::test_no_lookahead_leak`)
- 비용 적용 후 CAGR이 적용 전보다 낮음(`test_costs_reduce_reported_cagr`)
- `simulation_runs`에 `oos_cagr`/`deflated_sharpe`/`gate_passed` 기록
- `algo_optimizer`가 `gate_passed=0` 파라미터 미반영
- 생존편향 경고가 리포트에 노출
- 신규 테스트 전부 통과 + 기존 테스트 회귀 없음

---

## 6. 주의할 함정 (이전 분석에서 도출)

- **미래참조 누수**: `calculated_metrics`를 그대로 읽으면 안 됨 — 반드시 `point_in_time.get_metrics_asof`로 PIT 재무에서 재계산.
- **생존편향 완전제거 불가**: 현재 데이터엔 상장폐지 종목 과거 시세가 없음. **제거하려 하지 말고 측정·경고**(`bias_report`)만.
- **세율/호가단위 시점성**: 과거 구간 백테스트는 그 시점의 세율(`sell_tax_rate(date)`)과 호가단위를 써야 함.
- **Deflated Sharpe의 n_trials**: 시뮬레이션이 탐색한 파라미터 공간 크기를 넘겨야 다중검정 보정이 의미 있음.

---

다음: 진행 위치에 맞는 체크포인트 문서로 이동하세요.
`01-codex-point-in-time.md` · `02-codex-execution-model.md` · `03-codex-validation-and-integration.md`
