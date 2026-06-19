"""호출 간 최소 간격을 보장하는 Rate Limit 데코레이터.

02-외부-API-가이드.md §12. Python 3.9 호환.
"""
import time
import functools


def rate_limited(min_interval: float = 1.0):
    """함수 호출 간 최소 대기 시간을 보장한다."""
    last_called = [0.0]

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            result = func(*args, **kwargs)
            last_called[0] = time.time()
            return result
        return wrapper
    return decorator
