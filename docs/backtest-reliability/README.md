# 백테스트 신뢰성 레이어 — 문서 세트

TTAK Quant 백테스트/시뮬레이션 엔진의 4대 편향(생존편향·미래참조·체결비현실성·과최적화)을
점진적 레이어로 보정하기 위한 설계·구현·핸드오프 문서 모음입니다.

## 읽는 순서

| 문서 | 용도 | 대상 |
|------|------|------|
| [`00-스펙-설계.md`](./00-스펙-설계.md) | 무엇을/왜 — 설계 명세 | 설계 검토 |
| [`01-구현-플랜.md`](./01-구현-플랜.md) | 어떻게 — Task 1~12 TDD 계획 | 구현 |
| [`codex-handoff/00-codex-시작가이드.md`](./codex-handoff/00-codex-시작가이드.md) | cold-start 부트스트랩 | **Codex/이어받는 에이전트** |
| [`codex-handoff/01-codex-point-in-time.md`](./codex-handoff/01-codex-point-in-time.md) | 체크포인트 ① (Task 1~3) | Codex |
| [`codex-handoff/02-codex-execution-model.md`](./codex-handoff/02-codex-execution-model.md) | 체크포인트 ② (Task 4~5) | Codex |
| [`codex-handoff/03-codex-validation-and-integration.md`](./codex-handoff/03-codex-validation-and-integration.md) | 체크포인트 ③ (Task 6~12) | Codex |

## 핸드오프 원칙

- 각 `codex-handoff/*` 문서는 **이전 대화 맥락 없이도** 작업을 이어받을 수 있도록 자급자족 작성됨.
- 토큰 소진/세션 중단 시: `codex-handoff/00-codex-시작가이드.md`의 **재개(Resume) 프로토콜**을 따라
  현재 진행 위치를 파악하고 해당 체크포인트 문서로 이동.
- 진행 방식: **TDD**(실패테스트 → 실패확인 → 최소구현 → 통과확인 → 커밋), 의존성 순서 T1→T12.

## 산출 배경

이 문서들은 superpowers `brainstorming`/`writing-plans` 방법론(맥락탐색 → 한 번에 한 질문씩 →
접근법 비교 → 설계합의 → spec → plan)에 따라 도출되었습니다. 통합 방식은 **Approach A
(기존 엔진에 점진적 신뢰성 레이어 추가)**, 데이터 제약은 **현재 보유 데이터 범위 내**입니다.
