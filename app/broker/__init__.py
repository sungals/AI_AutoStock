"""브로커 패키지 — config.BROKER_PROVIDER로 증권사 구현을 선택한다.

현재: 'kis'(한국투자증권). 추후: 'nh'(NH투자증권 나무) 등을 같은 인터페이스로 추가.
"""
from typing import Optional
import config
from broker.base import BrokerClient, OrderResult


def get_broker(provider: Optional[str] = None, http=None, mode: Optional[str] = None
               ) -> BrokerClient:
    """설정에 따라 브로커 클라이언트를 생성한다. http/mode 주입 가능(테스트용)."""
    provider = (provider or config.BROKER_PROVIDER or 'kis').lower()
    if provider == 'kis':
        from broker.kis import KISBroker
        return KISBroker(http=http, mode=mode)
    # 추후 NH투자증권(나무): from broker.nh import NHBroker
    raise ValueError('지원하지 않는 브로커: %s' % provider)


__all__ = ['BrokerClient', 'OrderResult', 'get_broker']
