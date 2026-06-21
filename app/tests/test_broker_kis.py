"""KIS 모의투자 브로커 스캐폴딩 — 네트워크/키 없이 HTTP 주입으로 검증."""
import json as _json

import broker
from broker.kis import KISBroker
from broker.base import OrderResult


class _Resp:
    def __init__(self, payload):
        self._payload = payload
    def json(self):
        return self._payload


class FakeHTTP:
    """requests 대체 — 호출 기록 + 미리 정한 응답 반환."""
    def __init__(self, responses):
        self.responses = responses        # {path_suffix: payload}
        self.calls = []                   # [(method, url, headers, body/params)]

    def _match(self, url):
        for suffix, payload in self.responses.items():
            if url.endswith(suffix) or suffix in url:
                return payload
        return {}

    def post(self, url, headers=None, json=None, timeout=None, **kw):
        self.calls.append(('POST', url, headers or {}, json or {}))
        return _Resp(self._match(url))

    def get(self, url, headers=None, params=None, timeout=None, **kw):
        self.calls.append(('GET', url, headers or {}, params or {}))
        return _Resp(self._match(url))


def _broker(mode='mock', http=None):
    return KISBroker(app_key='K', app_secret='S', account='12345678-01',
                     mode=mode, http=http)


def test_default_mode_is_mock_and_url():
    b = _broker()
    assert b.is_mock() is True
    assert 'openapivts' in b.base_url        # 모의투자 도메인
    assert b.cano == '12345678' and b.acnt_prdt_cd == '01'


def test_issue_token_parses_access_token():
    http = FakeHTTP({'/oauth2/tokenP': {'access_token': 'TOKEN123'}})
    b = _broker(http=http)
    assert b.issue_token() == 'TOKEN123'
    assert http.calls[0][0] == 'POST'


def test_get_price_parses_current_price():
    http = FakeHTTP({
        '/oauth2/tokenP': {'access_token': 'T'},
        'inquire-price': {'output': {'stck_prpr': '70500'}},
    })
    assert _broker(http=http).get_price('005930') == 70500


def test_mock_buy_uses_mock_tr_id_and_parses_order_id():
    http = FakeHTTP({
        '/oauth2/tokenP': {'access_token': 'T'},
        'order-cash': {'rt_cd': '0', 'msg1': '주문 전송 완료', 'output': {'ODNO': '0001234567'}},
    })
    b = _broker(http=http)
    res = b.place_order('005930', 'buy', qty=10, price=70000)
    assert isinstance(res, OrderResult) and res.ok is True
    assert res.order_id == '0001234567'
    # 모의투자 매수 tr_id 사용 확인
    order_call = [c for c in http.calls if 'order-cash' in c[1]][0]
    assert order_call[2]['tr_id'] == 'VTTC0802U'
    assert order_call[3]['ORD_QTY'] == '10' and order_call[3]['ORD_DVSN'] == '00'


def test_prod_order_blocked_without_allow_live():
    http = FakeHTTP({'/oauth2/tokenP': {'access_token': 'T'}})
    b = _broker(mode='prod', http=http)
    assert b.is_mock() is False
    res = b.place_order('005930', 'buy', qty=1, price=70000)   # allow_live 없음
    assert res.ok is False
    assert 'LIVE order blocked' in res.message
    # 실주문 차단 시 order-cash 호출이 발생하지 않아야 함
    assert not any('order-cash' in c[1] for c in http.calls)


def test_prod_order_allowed_with_explicit_flag_uses_prod_tr_id():
    http = FakeHTTP({
        '/oauth2/tokenP': {'access_token': 'T'},
        'order-cash': {'rt_cd': '0', 'output': {'ODNO': '9'}},
    })
    b = _broker(mode='prod', http=http)
    res = b.place_order('005930', 'sell', qty=2, price=0, order_type='market',
                        allow_live=True)
    assert res.ok is True
    order_call = [c for c in http.calls if 'order-cash' in c[1]][0]
    assert order_call[2]['tr_id'] == 'TTTC0801U'      # 실전 매도
    assert order_call[3]['ORD_DVSN'] == '01'           # 시장가


def test_invalid_order_inputs():
    b = _broker(http=FakeHTTP({}))
    assert b.place_order('005930', 'hold', 10).ok is False
    assert b.place_order('005930', 'buy', 0).ok is False


def test_factory_returns_kis_broker():
    b = broker.get_broker(provider='kis', http=FakeHTTP({}), mode='mock')
    assert isinstance(b, KISBroker) and b.is_mock()


def test_factory_rejects_unknown_provider():
    try:
        broker.get_broker(provider='unknown')
        assert False, 'should raise'
    except ValueError:
        pass
