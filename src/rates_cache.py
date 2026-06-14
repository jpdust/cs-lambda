import threading
from typing import Optional

from .models import CurrencyRatesResponse


class RatesCache:
    """Thread-safe in-memory cache for the last successful rates response.

    Used as a fallback when the upstream API is temporarily unavailable.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cached: Optional[CurrencyRatesResponse] = None

    def store(self, response: CurrencyRatesResponse) -> None:
        with self._lock:
            self._cached = response

    def get(self) -> Optional[CurrencyRatesResponse]:
        with self._lock:
            return self._cached

    def clear(self) -> None:
        with self._lock:
            self._cached = None
