"""Unit tests for CurrencyService — mirrors CurrencyServiceTest.java."""

from decimal import Decimal

import pytest
import requests.exceptions
import responses as resp

from src.exceptions import ExternalApiException, NetworkException
from src.models import CurrencyRatesResponse
from tests.conftest import SAMPLE_UPSTREAM, UPSTREAM_URL


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@resp.activate
def test_fetch_rates_returns_deserialized_response(service):
    resp.get(UPSTREAM_URL, json=SAMPLE_UPSTREAM)

    result = service.fetch_rates()

    assert result.stale is False
    assert result.rates.success is True
    assert result.rates.source == "USD"
    assert result.rates.date == "2026-06-09T04:33:00+0000"
    assert result.rates.rates["EUR"] == Decimal("0.9235")
    assert result.rates.rates["GBP"] == Decimal("0.7885")
    assert result.rates.rates["JPY"] == Decimal("154.32")


@resp.activate
def test_fetch_rates_rates_are_sorted_ascending_by_currency_code(service):
    resp.get(UPSTREAM_URL, json=SAMPLE_UPSTREAM)

    result = service.fetch_rates()

    keys = list(result.rates.rates.keys())
    assert keys == sorted(keys)


@resp.activate
def test_fetch_rates_stores_successful_response_in_cache(service, cache):
    resp.get(UPSTREAM_URL, json=SAMPLE_UPSTREAM)

    service.fetch_rates()

    assert cache.get() is not None
    assert cache.get().source == "USD"


# ---------------------------------------------------------------------------
# Request verification
# ---------------------------------------------------------------------------

@resp.activate
def test_fetch_rates_sends_authorization_bearer_header(service):
    resp.get(UPSTREAM_URL, json=SAMPLE_UPSTREAM)

    service.fetch_rates()

    assert resp.calls[0].request.headers["Authorization"] == "Bearer test-key"


@resp.activate
def test_fetch_rates_sends_source_query_param(service):
    resp.get(UPSTREAM_URL, json=SAMPLE_UPSTREAM)

    service.fetch_rates()

    assert "source=USD" in resp.calls[0].request.url


@resp.activate
def test_fetch_rates_does_not_send_api_key_as_query_param(service):
    resp.get(UPSTREAM_URL, json=SAMPLE_UPSTREAM)

    service.fetch_rates()

    url = resp.calls[0].request.url
    assert "test-key" not in url
    assert "key" not in url.split("?", 1)[-1]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@resp.activate
def test_fetch_rates_empty_upstream_list_falls_back_to_configured_source(service):
    resp.get(UPSTREAM_URL, json=[])

    result = service.fetch_rates()

    assert result.rates.source == "USD"
    assert result.rates.date is None
    assert result.rates.rates == {}


@resp.activate
def test_fetch_rates_duplicate_currency_code_keeps_first_occurrence(service):
    upstream = [
        {"rate": 1.0, "source": "USD", "target": "EUR", "time": "2026-06-09T04:33:00+0000"},
        {"rate": 2.0, "source": "USD", "target": "EUR", "time": "2026-06-09T04:33:00+0000"},
    ]
    resp.get(UPSTREAM_URL, json=upstream)

    result = service.fetch_rates()

    assert result.rates.rates["EUR"] == Decimal("1.0")


# ---------------------------------------------------------------------------
# Error handling — cache populated (stale fallback)
# ---------------------------------------------------------------------------

@resp.activate
def test_fetch_rates_returns_stale_response_on_5xx_when_cache_populated(service, cache):
    cached = CurrencyRatesResponse(
        success=True, source="USD", date="old", rates={"EUR": Decimal("0.9")}
    )
    cache.store(cached)
    resp.get(UPSTREAM_URL, status=500)

    result = service.fetch_rates()

    assert result.stale is True
    assert result.rates is cached


@resp.activate
def test_fetch_rates_returns_stale_response_on_network_failure_when_cache_populated(
    service, cache
):
    cached = CurrencyRatesResponse(
        success=True, source="USD", date="old", rates={"EUR": Decimal("0.9")}
    )
    cache.store(cached)
    resp.get(UPSTREAM_URL, body=requests.exceptions.ConnectionError("down"))

    result = service.fetch_rates()

    assert result.stale is True
    assert result.rates is cached


# ---------------------------------------------------------------------------
# Error handling — cache empty (exception propagated)
# ---------------------------------------------------------------------------

@resp.activate
def test_fetch_rates_throws_external_api_exception_on_5xx_when_cache_empty(service):
    resp.get(UPSTREAM_URL, status=500)

    with pytest.raises(ExternalApiException) as exc_info:
        service.fetch_rates()

    assert exc_info.value.status_code == 500


@resp.activate
def test_fetch_rates_throws_external_api_exception_on_4xx_when_cache_empty(service):
    resp.get(UPSTREAM_URL, status=401)

    with pytest.raises(ExternalApiException) as exc_info:
        service.fetch_rates()

    assert exc_info.value.status_code == 401


@resp.activate
def test_fetch_rates_throws_network_exception_on_connection_failure_when_cache_empty(service):
    resp.get(UPSTREAM_URL, body=requests.exceptions.ConnectionError("unreachable"))

    with pytest.raises(NetworkException):
        service.fetch_rates()


@resp.activate
def test_fetch_rates_throws_network_exception_on_timeout_when_cache_empty(service):
    resp.get(UPSTREAM_URL, body=requests.exceptions.Timeout("timed out"))

    with pytest.raises(NetworkException):
        service.fetch_rates()
