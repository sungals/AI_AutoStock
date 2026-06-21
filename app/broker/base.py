"""브로커 추상화 — 증권사 연동의 공통 인터페이스.

KIS(한국투자증권)를 먼저 구현하고, 추후 NH투자증권(나무) 등을 같은 인터페이스로
갈아끼울 수 있도록 한다. 매매 로직은 이 인터페이스에만 의존한다.

안전 원칙:
- 기본은 모의투자(mock). 실주문(prod)은 명시적 allow_live=True가 있어야 한다.
- 네트워크 호출은 주입 가능(http)하여 키/네트워크 없이 테스트 가능.

Python 3.9 호환.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class OrderResult:
    """주문 실행 결과."""
    ok: bool
    order_id: Optional[str] = None
    message: str = ''
    raw: Dict = field(default_factory=dict)


class BrokerClient(ABC):
    """증권사 클라이언트 공통 인터페이스."""

    name = 'base'
    mode = 'mock'   # 'mock' | 'prod'

    def is_mock(self) -> bool:
        return self.mode != 'prod'

    @abstractmethod
    def get_price(self, stock_code: str) -> Optional[int]:
        """현재가(원). 실패 시 None."""

    @abstractmethod
    def get_balance(self) -> Dict:
        """계좌 잔고/보유 조회 (원시 응답 dict)."""

    @abstractmethod
    def place_order(self, stock_code: str, side: str, qty: int, price: int = 0,
                    order_type: str = 'limit', allow_live: bool = False) -> OrderResult:
        """주문 실행.

        side: 'buy' | 'sell'
        order_type: 'limit'(지정가) | 'market'(시장가)
        allow_live: prod 모드에서 실주문을 내려면 반드시 True (안전 가드).
        """
