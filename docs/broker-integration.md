# 증권사 연동 (자동매매) — KIS 모의투자 스캐폴딩 + 나무증권 검토

> 갱신: 2026-06-21. 코드: `app/broker/`. 테스트: `app/venv/bin/python -m pytest tests/test_broker_kis.py`

## ⚠️ 대전제

이 스캐폴딩은 **주문 실행 계층의 토대**일 뿐, 실자금 매매 준비가 끝난 것이 아니다.
앞선 점검(데이터 이상치·생존편향·강세장 편향·체결/정합성/킬스위치 부재)이 해소되기 전까지
**실계좌(prod) 사용 금지**. 기본은 모의투자(mock).

## 아키텍처 — 브로커 추상화

증권사를 갈아끼울 수 있도록 공통 인터페이스에만 매매 로직이 의존한다.

```
broker/
├── base.py    BrokerClient(ABC) + OrderResult      # 공통 인터페이스
├── kis.py     KISBroker(BrokerClient)              # 한국투자증권 (구현)
└── __init__.py get_broker()  ← config.BROKER_PROVIDER로 선택
                # 추후: nh.py  NHBroker(BrokerClient)  (NH투자증권 나무)
```

인터페이스(`BrokerClient`): `get_price`, `get_balance`, `place_order(side, qty, price, order_type, allow_live)`.

## KIS(한국투자증권) 모의투자 — 구현됨

| 기능 | 구현 |
|------|------|
| 토큰 발급 | `POST /oauth2/tokenP` |
| 현재가 | `GET .../quotations/inquire-price` (tr_id FHKST01010100) |
| 잔고 | `GET .../trading/inquire-balance` (mock VTTC8434R / prod TTTC8434R) |
| 현금주문 | `POST .../trading/order-cash` (매수 VTTC0802U / 매도 VTTC0801U, 실전은 TTTC…) |
| 모의/실전 분기 | mock=`openapivts…:29443`, prod=`openapi…:9443` |

**안전 장치**:
- 기본 `KOREAINVESTMENT_MODE=mock`.
- `place_order`는 **prod 모드에서 `allow_live=True`가 없으면 주문 자체를 거부**(네트워크 호출 안 함).
- 모든 HTTP는 주입 가능(`http=`) → 키·네트워크 없이 단위테스트. (테스트 9건, 전체 125 passed)

**남은 작업(스캐폴딩 이후)**: 토큰 만료/재발급·hashkey, 주문 체결/미체결/취소 추적,
멱등키(중복주문 방지), 잔고 reconciliation, WebSocket 실시간 체결, live_trades 기록 연동,
킬스위치·일일손실 집행, 페이퍼 트레이딩 수개월.

### 사용 (키 투입 후)
```python
import broker
b = broker.get_broker()          # config.BROKER_PROVIDER='kis', mode='mock'
b.get_price('005930')
b.place_order('005930', 'buy', qty=1, price=70000)   # 모의투자
```
`.env`에 `KOREAINVESTMENT_APP_ID/SECRET/ACCOUNT` + `KOREAINVESTMENT_MODE=mock` 설정.

## 나무증권(NH투자증권) 연동 — 가능성 검토

**구조적으로는 가능**: `broker/nh.py`에 `NHBroker(BrokerClient)`를 같은 인터페이스로
구현하고 `BROKER_PROVIDER=nh`로 바꾸면 매매 로직 수정 없이 교체된다.

단, **실무적으로 먼저 확인할 점**(NH 공식 OpenAPI 문서로 검증 필요):

| 확인 항목 | 왜 중요한가 |
|-----------|-------------|
| **API 방식: REST vs OCX/COM** | NH(나무/QV) OpenAPI는 전통적으로 **Windows COM/OCX 기반**(키움 OpenAPI+ 유사)일 가능성. 그렇다면 macOS/Linux 서버에서 **직접 호출 불가** → 별도 Windows 호스트에 OCX를 띄우고 로컬 REST 브리지를 두는 구조 필요 |
| **모의투자(mock) 환경 제공 여부** | KIS는 전용 모의 도메인(openapivts)이 있으나, NH는 동등한 공개 모의 환경이 없을 수 있음 → 페이퍼 트레이딩 난이도에 직결 |
| **주문/잔고/실시간 커버리지** | 현금주문·체결통보·잔고·실시간 시세 지원 범위 확인 |
| **승인/심사·약관** | 개인 OpenAPI 발급 조건·한도 |

**권고**: KIS는 한국 리테일 알고매매에서 **가장 현대적인 REST+WebSocket OpenAPI + 공식
모의투자 + 풍부한 문서**를 제공한다. 따라서 **전체 매매 스택을 KIS 모의로 먼저 완성·검증**하고,
NH로 전환할 시점에 위 항목을 확인해 `NHBroker`를 구현한다. NH가 OCX 전용이면 Windows 브리지
설계가 추가로 필요하다.

> 참고: 위 NH API 특성은 일반적 경향에 기반한 것으로, **NH투자증권 공식 OpenAPI 최신 문서로
> 반드시 재확인**해야 한다(REST 제공 여부·모의 환경이 바뀌었을 수 있음).

## 페이퍼 트레이딩 루프 — 구현됨 (스캐폴딩)

시그널(예: value 스크리닝 상위)을 **모의 브로커로 매수 집행하고 live_trades에 기록**한다.

| 모듈 | 역할 |
|------|------|
| `broker/memory.py` | `MemoryBroker` — 네트워크 없는 인메모리 브로커(결정적 테스트·로컬 검증) |
| `db_portfolio.py` | `record_live_trade`, `get_live_holdings`, `update_live_cash`, `has_live_buy` |
| `paper_trader.py` | `run_paper_session(picks)`, `reconcile()`, `positions_from_kis_balance()` |

**안전·규칙**:
- **모의 포트폴리오 + 모의 브로커만** 허용(live/prod면 거부).
- **멱등성**: 같은 날 같은 종목 재매수 안 함. 이미 보유 종목 스킵.
- **사이징**: 종목당 `max_position_size`(기본 20%) × 초기자본, 현금 한도 내.
- **정합성**: `reconcile()`로 DB 보유 vs 브로커 잔고 비교(불일치 탐지).

E2E 확인: 실 value 상위 5종목 → 모의 매수 5건, 현금 차감, **DB↔브로커 일치(matched)**.
테스트 7건(인메모리 브로커, 오프라인). **전체 132 passed.**

```python
import db_portfolio, paper_trader
from broker.memory import MemoryBroker   # 또는 broker.get_broker()로 KIS mock
pid = db_portfolio.create_live_portfolio(conn, 'paper', 10_000_000, mode='mock')
paper_trader.run_paper_session(conn, pid, ['000270','005930'], broker=MemoryBroker(prices={...}))
paper_trader.reconcile(conn, pid, broker)
```

**남은 작업**: 리밸런싱, 실시간 체결통보(WebSocket) 기반 상태추적,
KIS mock 라이브 검증(키 투입), 성과/추적오차 기록.

## EOD 파이프라인 연결 — 구현됨

`run_daily_pipeline.py`에 **`paper_trade` 스테이지**를 fusion 직후에 추가.

- **기본 OFF**(`do_paper_trade=False`) — 자동매매는 명시적으로 켤 때만.
- **오프라인 페이퍼**: DB 최신 종가로 가격을 매기는 MemoryBroker(키·네트워크 불필요),
  모의 포트폴리오 `eod-paper`(없으면 생성).
- 흐름: **청산 먼저**(`exit_manager.run_exits`) → **진입**(`paper_trader.run_paper_session`,
  기본 value 상위 N) → 리스크 게이트(킬스위치·일일손실) 자동 적용.
- CLI: `--paper-trade [--trade-strategy value] [--trade-top-n 10]`.

E2E(실 DB): value 상위 6 → 청산 0 / 진입 5, 현금 차감 확인. 스테이지 순서:
`… screening → fusion → paper_trade → simulation → optimize → report`.
테스트: 파이프라인 스테이지 순서 + 모의매매 실행. **전체 146 passed.**

```bash
python run_daily_pipeline.py --paper-trade --trade-strategy value --trade-top-n 10
```

## 청산(매도/손절) 로직 — 구현됨

`exit_manager.py` + 순수함수 `portfolio_operations.check_stop_loss/trailing_stop/timeout_exit`.

| 규칙 | 기준(기본) | 비고 |
|------|-----------|------|
| 하드 손절 | 진입가 대비 −10% (`EXIT_STOP_LOSS_PCT`) | 우선순위 1 |
| 트레일링 스탑 | 진입 후 최고가 대비 −8% (`EXIT_TRAIL_PCT`) | 최고가는 price_data로 산출 |
| 보유기간 초과 | 90일 (`EXIT_MAX_HOLD_DAYS`) | |

- `run_exits()`가 보유 포지션을 점검해 규칙 충족 시 **전량 매도**(모의), live_trades에
  `exit_reason`·실현손익(pnl_pct) 기록, 현금 환입.
- **청산은 킬스위치와 무관하게 항상 허용**(손절을 막으면 안 됨 — 테스트로 검증).
- `db_portfolio.get_live_positions()`로 진입가/진입일/수량 추적.

테스트 7건(손절/트레일/타임아웃/홀드/손익기록/킬스위치무관). **전체 145 passed.**

```python
import exit_manager
exit_manager.run_exits(conn, pid, broker, trade_date='2026-06-21')
# → {'sold':1,'held':2,'failed':0,'exits':[{'stock_code':'A','reason':'stop_loss','pnl_pct':-11.0,...}]}
```

## 킬스위치 + 일일 손실한도 집행 — 구현됨

`risk_guard.py` + 테이블 `risk_state`(킬스위치), `risk_daily`(일 기준 평가액).

| 기능 | 설명 |
|------|------|
| 전역 킬스위치(config) | `TRADING_KILL_SWITCH=1` → 모든 포트폴리오 신규 진입 차단(마스터 비상정지) |
| 전역 킬스위치(DB) | `trip_kill_switch(conn, 0, reason)` — portfolio_id=0 = 전역 |
| 포트폴리오 킬스위치 | `trip_kill_switch(conn, pid, reason)` / `reset_kill_switch` |
| 일일 손실한도 | 세션 시작 평가액 대비 손실이 `daily_loss_limit`(기본 3%) 이상이면 **킬스위치 자동 트립** |
| 통합 게이트 | `pre_trade_check()` — `paper_trader`가 매매 직전 호출, 차단 시 주문 안 나감 |

집행 흐름: `run_paper_session` → `pre_trade_check`(킬스위치 → 일일손실) → 통과해야 매수.
한 번 트립되면 **가격이 회복돼도 지속**(수동 `reset` 전까지). 테스트 6건, 전체 138 passed.

```python
import risk_guard
risk_guard.trip_kill_switch(conn, pid, '수동 정지')     # 비상정지
risk_guard.reset_kill_switch(conn, pid)                  # 재개
risk_guard.pre_trade_check(conn, pid, broker.get_price, '2026-06-21')
# → {'allowed': False, 'reason': '일일 손실한도 초과 (4.0% ≥ 3.0%)'} 등
```
