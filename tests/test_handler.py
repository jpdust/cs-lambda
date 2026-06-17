"""Tests for the Lambda handler route logic — mirrors CurrencyControllerTest.java."""

import json
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from handler import _handle_get_rates
from src.exceptions import ExternalApiException, NetworkException
from src.models import CurrencyRatesResponse, RatesFetchResult
from tests.conftest import make_event

CACHE_CONTROL = "public, max-age=300, stale-if-error=86400"

SAMPLE_RATES = CurrencyRatesResponse(
    success=True,
    source="USD",
    date="2026-06-09T04:33:00+0000",
    rates={"EUR": Decimal("0.9235"), "GBP": Decimal("0.7885")},
)


def _make_service(rates: CurrencyRatesResponse, stale: bool = False):
    svc = MagicMock()
    svc.fetch_rates.return_value = RatesFetchResult(rates=rates, stale=stale)
    return svc


def test_get_rates_returns_200_with_rates_body():
    svc = _make_service(SAMPLE_RATES)

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["success"] is True
    assert body["source"] == "USD"
    assert body["date"] == "2026-06-09T04:33:00+0000"
    assert body["rates"]["EUR"] == pytest.approx(0.9235)
    assert body["rates"]["GBP"] == pytest.approx(0.7885)


def test_get_rates_includes_cache_control_header():
    svc = _make_service(SAMPLE_RATES)

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert result["headers"]["Cache-Control"] == CACHE_CONTROL


def test_get_rates_does_not_include_stale_header_when_fresh():
    svc = _make_service(SAMPLE_RATES, stale=False)

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert "X-Rates-Stale" not in result["headers"]


def test_get_rates_includes_stale_header_when_serving_cached_rates():
    svc = _make_service(SAMPLE_RATES, stale=True)

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert result["headers"].get("X-Rates-Stale") == "true"


def test_get_rates_returns_503_when_upstream_fails_and_cache_empty():
    svc = MagicMock()
    svc.fetch_rates.side_effect = ExternalApiException("HTTP 500", 500)

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert result["statusCode"] == 503


def test_get_rates_returns_503_when_network_error():
    svc = MagicMock()
    svc.fetch_rates.side_effect = NetworkException("Connection refused")

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert result["statusCode"] == 503
    body = json.loads(result["body"])
    assert body["type"] == "urn:currency-service:network-error"


def test_lambda_handler_routes_get_api_rates(monkeypatch):
    import handler as h

    svc = _make_service(SAMPLE_RATES)
    monkeypatch.setattr(h, "_service", svc)
    monkeypatch.setattr(h, "_cache_control", CACHE_CONTROL)

    result = h.lambda_handler(make_event("GET", "/api/rates"), None)

    assert result["statusCode"] == 200


def test_lambda_handler_returns_404_for_unknown_path(monkeypatch):
    import handler as h

    result = h.lambda_handler(make_event("GET", "/unknown"), None)

    assert result["statusCode"] == 404
