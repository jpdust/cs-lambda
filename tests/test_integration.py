"""Full-stack integration tests — mirrors CurrencyRatesIntegrationTest.java.

These tests use `responses` to mock the upstream HTTP API and exercise the complete
call chain: lambda_handler → CurrencyService → upstream mock → response.
"""

import json
from decimal import Decimal

import pytest
import requests.exceptions
import responses as resp

import handler as h
from src.config import Config
from src.currency_service import CurrencyService
from src.models import CurrencyRatesResponse
from src.rates_cache import RatesCache
from tests.conftest import SAMPLE_UPSTREAM, UPSTREAM_BASE, UPSTREAM_PATH, UPSTREAM_URL, make_event


@pytest.fixture(autouse=True)
def isolated_handler(monkeypatch):
    """Replace the module-level singletons with fresh instances pointing at the test upstream."""
    cfg = Config(
        base_url=UPSTREAM_BASE,
        path=UPSTREAM_PATH,
        source="USD",
        api_key="test-key",
        cache_max_age=300,
        stale_if_error=86400,
    )
    fresh_cache = RatesCache()
    fresh_service = CurrencyService(cache=fresh_cache, config=cfg)
    cache_control = f"public, max-age={cfg.cache_max_age}, stale-if-error={cfg.stale_if_error}"

    monkeypatch.setattr(h, "_config", cfg)
    monkeypatch.setattr(h, "_cache", fresh_cache)
    monkeypatch.setattr(h, "_service", fresh_service)
    monkeypatch.setattr(h, "_cache_control", cache_control)

    # Expose cache so individual tests can pre-populate it
    return {"cache": fresh_cache, "service": fresh_service}


@resp.activate
def test_get_rates_returns_ok_with_rates_body():
    resp.get(UPSTREAM_URL, json=SAMPLE_UPSTREAM)

    result = h.lambda_handler(make_event(), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["success"] is True
    assert body["source"] == "USD"
    assert "EUR" in body["rates"]
    assert "GBP" in body["rates"]
    assert "JPY" in body["rates"]


@resp.activate
def test_get_rates_includes_cache_control_header():
    resp.get(UPSTREAM_URL, json=SAMPLE_UPSTREAM)

    result = h.lambda_handler(make_event(), None)

    assert result["headers"]["Cache-Control"] == "public, max-age=300, stale-if-error=86400"


@resp.activate
def test_get_rates_returns_503_when_upstream_fails_and_cache_empty():
    resp.get(UPSTREAM_URL, status=500)

    result = h.lambda_handler(make_event(), None)

    assert result["statusCode"] == 503
    body = json.loads(result["body"])
    assert body["type"] == "urn:currency-service:upstream-error"


@resp.activate
def test_get_rates_forwards_source_and_authorization_to_upstream():
    resp.get(UPSTREAM_URL, json=SAMPLE_UPSTREAM)

    h.lambda_handler(make_event(), None)

    request = resp.calls[0].request
    assert request.headers.get("Authorization") == "Bearer test-key"
    assert "source=USD" in request.url


@resp.activate
def test_get_rates_returns_stale_rates_with_header_when_upstream_fails_and_cache_populated(
    isolated_handler,
):
    cached = CurrencyRatesResponse(
        success=True,
        source="USD",
        date="2026-06-08T00:00:00+0000",
        rates={"EUR": Decimal("0.91")},
    )
    isolated_handler["cache"].store(cached)
    resp.get(UPSTREAM_URL, status=503)

    result = h.lambda_handler(make_event(), None)

    assert result["statusCode"] == 200
    assert result["headers"].get("X-Rates-Stale") == "true"
    body = json.loads(result["body"])
    assert body["rates"]["EUR"] == pytest.approx(0.91)
