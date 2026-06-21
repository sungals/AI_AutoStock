"""인메모리 브로커 — 네트워크 없는 결정적 페이퍼 트레이딩(테스트·로컬 검증용).

KIS 모의투자와 동일한 BrokerClient 인터페이스를 구현하되, 주문을 메모리상의
포지션에만 반영한다. 항상 mock. Python 3.9 호환.
"""
from typing import Optional, Dict
from broker.base import BrokerClient, OrderResult


class MemoryBroker(BrokerClient):
    name = 'memory'
    mode = 'mock'

    def __init__(self, prices: Optional[Dict[str, int]] = None):
        self.prices = dict(prices or {})        # {stock_code: 현재가}
        self.positions = {}                     # type: Dict[str, int]
        self._seq = 0

    def get_price(self, stock_code: str) -> Optional[int]:
        return self.prices.get(stock_code)

    def get_balance(self) -> Dict:
        return {'positions': dict(self.positions)}

    def place_order(self, stock_code: str, side: str, qty: int, price: int = 0,
                    order_type: str = 'limit', allow_live: bool = False) -> OrderResult:
        if side not in ('buy', 'sell') or qty <= 0:
            return OrderResult(ok=False, message='invalid order')
        sign = 1 if side == 'buy' else -1
        self.positions[stock_code] = self.positions.get(stock_code, 0) + sign * qty
        if self.positions[stock_code] == 0:
            del self.positions[stock_code]
        self._seq += 1
        return OrderResult(ok=True, order_id='M%06d' % self._seq, message='filled')
