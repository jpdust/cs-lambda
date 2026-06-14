import threading
from decimal import Decimal

import pytest

from src.models import CurrencyRatesResponse
from src.rates_cache import RatesCache

SAMPLE = CurrencyRatesResponse(
    success=True,
    source="USD",
    date="2026-06-09T04:33:00+0000",
    rates={"EUR": Decimal("0.9235")},
)


def test_get_returns_none_when_empty():
    cache = RatesCache()
    assert cache.get() is None


def test_store_and_get_returns_stored_value():
    cache = RatesCache()
    cache.store(SAMPLE)
    assert cache.get() is SAMPLE


def test_store_overwrites_previous_value():
    cache = RatesCache()
    first = CurrencyRatesResponse(success=True, source="USD", date=None, rates={})
    cache.store(first)
    cache.store(SAMPLE)
    assert cache.get() is SAMPLE


def test_clear_removes_cached_value():
    cache = RatesCache()
    cache.store(SAMPLE)
    cache.clear()
    assert cache.get() is None


def test_thread_safety_concurrent_stores():
    cache = RatesCache()
    errors: list[Exception] = []

    def store_many():
        try:
            for _ in range(1000):
                cache.store(SAMPLE)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=store_many) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert cache.get() is not None
