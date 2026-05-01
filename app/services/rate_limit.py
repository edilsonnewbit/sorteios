"""Rate limiting simples em memória (sliding window)."""
import time
from collections import defaultdict, deque
import threading

_lock = threading.Lock()
_windows: dict[str, deque] = defaultdict(deque)


def is_allowed(key: str, max_calls: int, window_seconds: int) -> bool:
    """Retorna True se a chamada está dentro do limite, False se excedeu."""
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        dq = _windows[key]
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= max_calls:
            return False
        dq.append(now)
        return True


def checkout_allowed(ip: str) -> bool:
    """Máximo de 10 checkouts por IP por minuto."""
    return is_allowed(f"checkout:{ip}", max_calls=10, window_seconds=60)


def order_query_allowed(ip: str) -> bool:
    """Máximo de 30 consultas de pedido por IP por minuto."""
    return is_allowed(f"order_query:{ip}", max_calls=30, window_seconds=60)


def login_allowed(ip: str) -> bool:
    """Máximo de 5 tentativas de login por IP por 5 minutos."""
    return is_allowed(f"login:{ip}", max_calls=5, window_seconds=300)
