"""한국투자증권(KIS) OpenAPI 클라이언트 — 모의투자(mock) 우선.

토큰 발급 → 현재가/잔고 조회 → 현금주문(매수/매도). 모든 HTTP는 주입 가능(http)하여
키/네트워크 없이 단위테스트 가능. 02-외부-API-가이드.md §6. Python 3.9 호환.

⚠️ 안전: 기본 mock. prod 실주문은 place_order(..., allow_live=True)가 있어야만 전송.
"""
from typing import Optional, Dict
import config
from rate_limit import rate_limited
from broker.base import BrokerClient, OrderResult

# KIS 거래 ID (tr_id) — 모의/실전 × 매수/매도가 다르다.
_TR_ID = {
    ('order', 'buy', 'mock'): 'VTTC0802U',
    ('order', 'buy', 'prod'): 'TTTC0802U',
    ('order', 'sell', 'mock'): 'VTTC0801U',
    ('order', 'sell', 'prod'): 'TTTC0801U',
    ('balance', 'mock'): 'VTTC8434R',
    ('balance', 'prod'): 'TTTC8434R',
}
_TR_PRICE = 'FHKST01010100'   # 현재가 조회(모의/실전 공통)


class KISBroker(BrokerClient):
    name = 'kis'

    def __init__(self, app_key: Optional[str] = None, app_secret: Optional[str] = None,
                 account: Optional[str] = None, mode: Optional[str] = None, http=None):
        self.app_key = app_key if app_key is not None else config.KIS_APP_KEY
        self.app_secret = app_secret if app_secret is not None else config.KIS_APP_SECRET
        self.account = account if account is not None else config.KIS_ACCOUNT
        self.mode = (mode or config.KIS_MODE or 'mock')
        self.base_url = config.KIS_MOCK_URL if self.is_mock() else config.KIS_PROD_URL
        if http is None:
            import requests
            http = requests
        self._http = http
        self._token = None  # type: Optional[str]

    # 계좌번호 'XXXXXXXX-XX' → CANO(8) / ACNT_PRDT_CD(2)
    @property
    def cano(self) -> str:
        return self.account.split('-')[0] if '-' in self.account else self.account[:8]

    @property
    def acnt_prdt_cd(self) -> str:
        return self.account.split('-')[1] if '-' in self.account else self.account[8:10]

    def _env(self) -> str:
        return 'mock' if self.is_mock() else 'prod'

    # ── 인증 ──
    @rate_limited(0.2)
    def issue_token(self) -> Optional[str]:
        resp = self._http.post(
            self.base_url + '/oauth2/tokenP',
            json={'grant_type': 'client_credentials',
                  'appkey': self.app_key, 'appsecret': self.app_secret},
            timeout=10)
        data = resp.json()
        self._token = data.get('access_token')
        return self._token

    def _headers(self, tr_id: str) -> Dict:
        if not self._token:
            self.issue_token()
        return {
            'authorization': 'Bearer %s' % (self._token or ''),
            'appkey': self.app_key,
            'appsecret': self.app_secret,
            'tr_id': tr_id,
            'custtype': 'P',
            'content-type': 'application/json; charset=utf-8',
        }

    # ── 조회 ──
    @rate_limited(0.2)
    def get_price(self, stock_code: str) -> Optional[int]:
        resp = self._http.get(
            self.base_url + '/uapi/domestic-stock/v1/quotations/inquire-price',
            headers=self._headers(_TR_PRICE),
            params={'FID_COND_MRKT_DIV_CODE': 'J', 'FID_INPUT_ISCD': stock_code},
            timeout=10)
        out = (resp.json() or {}).get('output') or {}
        px = out.get('stck_prpr')
        try:
            return int(px) if px not in (None, '') else None
        except (ValueError, TypeError):
            return None

    @rate_limited(0.2)
    def get_balance(self) -> Dict:
        tr = _TR_ID[('balance', self._env())]
        resp = self._http.get(
            self.base_url + '/uapi/domestic-stock/v1/trading/inquire-balance',
            headers=self._headers(tr),
            params={
                'CANO': self.cano, 'ACNT_PRDT_CD': self.acnt_prdt_cd,
                'AFHR_FLPR_YN': 'N', 'OFL_YN': '', 'INQR_DVSN': '02',
                'UNPR_DVSN': '01', 'FUND_STTL_ICLD_YN': 'N',
                'FNCG_AMT_AUTO_RDPT_YN': 'N', 'PRCS_DVSN': '00',
                'CTX_AREA_FK100': '', 'CTX_AREA_NK100': '',
            },
            timeout=10)
        return resp.json() or {}

    # ── 주문 ──
    def place_order(self, stock_code: str, side: str, qty: int, price: int = 0,
                    order_type: str = 'limit', allow_live: bool = False) -> OrderResult:
        if side not in ('buy', 'sell'):
            return OrderResult(ok=False, message="side must be 'buy' or 'sell'")
        if qty <= 0:
            return OrderResult(ok=False, message='qty must be > 0')
        # 안전 가드: 실계좌 주문은 명시적 allow_live=True 필수
        if not self.is_mock() and not allow_live:
            return OrderResult(
                ok=False,
                message='LIVE order blocked — prod 모드 실주문은 allow_live=True 필요')

        tr = _TR_ID[('order', side, self._env())]
        ord_dvsn = '01' if order_type == 'market' else '00'   # 01=시장가, 00=지정가
        body = {
            'CANO': self.cano, 'ACNT_PRDT_CD': self.acnt_prdt_cd,
            'PDNO': stock_code, 'ORD_DVSN': ord_dvsn,
            'ORD_QTY': str(int(qty)),
            'ORD_UNPR': str(int(price) if order_type == 'limit' else 0),
        }
        resp = self._http.post(
            self.base_url + '/uapi/domestic-stock/v1/trading/order-cash',
            headers=self._headers(tr), json=body, timeout=10)
        data = resp.json() or {}
        ok = data.get('rt_cd') == '0'
        order_id = (data.get('output') or {}).get('ODNO')
        return OrderResult(ok=ok, order_id=order_id,
                           message=data.get('msg1', ''), raw=data)
