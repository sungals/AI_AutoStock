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
