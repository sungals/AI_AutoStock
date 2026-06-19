# AI_AutoStock 공통 작업지시서

이 파일은 Codex와 Claude가 함께 바라보는 단일 작업지시서다. 에이전트별 작업 메모는
`agents/codex/`와 `agents/claude/`에 분리하되, 구현 기준과 진행 규칙은 이 파일을 우선한다.

## 프로젝트 현재 상태

- 앱 루트: `app/`
- 실행 DB: `app/quant_data.db` (Git 커밋 제외)
- 테스트: `cd app && venv/bin/python -m pytest tests/ -q`
- 로컬 웹: `cd app && PORT=5001 venv/bin/python web_app.py`
- 현재 웹 URL: `http://127.0.0.1:5001`

## 핵심 문서

1. `05-구현-가이드.md` — 전체 Phase 1~10 개발 기준
2. `04-DB-스키마.md` — 테이블 정의 기준
3. `docs/backtest-reliability/02-구현-진행현황.md` — 최신 구현 진행 현황
4. `docs/backtest-reliability/README.md` — 신뢰성 레이어 문서 인덱스

## 완료된 주요 범위

- DART/pykrx 데이터 수집
- 백테스트 신뢰성 레이어
- 기술적 분석, 11개 스크리닝 전략
- 뉴스 감성 분석, 매크로 수집, 융합 시그널
- 포트폴리오 기본 관리
- 인증이 적용된 Flask REST API와 서버 렌더링 대시보드

## 작업 원칙

- Python 3.9 호환 유지: `X | None` 문법 대신 `Optional[X]` 사용
- DB 함수는 가능한 connection injection 유지
- SQL 값은 파라미터 바인딩 사용
- 외부 API 키/쿠키/DB/venv는 커밋 금지
- 기능 변경 시 테스트 추가 또는 기존 테스트 갱신
- 작업 완료 전 최소 `cd app && venv/bin/python -m pytest tests/ -q` 실행
- `docs/backtest-reliability/02-구현-진행현황.md`에 큰 변경 요약 기록

## 에이전트 작업 분리 규칙

- Codex 전용 메모/계획/핸드오프: `agents/codex/`
- Claude 전용 메모/계획/핸드오프: `agents/claude/`
- 공통 지시: 이 파일 `agent.md`
- 양쪽 에이전트는 작업 시작 시 반드시 `agent.md`와 각자 폴더의 `README.md`를 먼저 읽는다.
- 서로의 작업 폴더는 필요한 경우 읽을 수 있지만, 상대 폴더의 파일을 수정할 때는 변경 이유를 명확히 남긴다.

## 현재 운영상 주의점

- `app/.env`에는 DART/Naver 키가 들어가며 Git 커밋 금지
- `app/cookies.txt`는 로그인 세션 쿠키라 Git 커밋 금지
- `app/quant_data.db*`는 실행 데이터라 Git 커밋 금지
- Naver API는 429가 발생할 수 있으므로 뉴스 수집기는 부분 수집 후 `errors`를 기록한다.
- macOS Python LibreSSL 환경에서 `urllib3` 경고가 보일 수 있으나 현재 테스트 영향은 없다.
