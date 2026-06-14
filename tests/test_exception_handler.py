"""Tests for exception-to-response mapping — mirrors GlobalExceptionHandlerTest.java."""

import json
from unittest.mock import MagicMock

from handler import _handle_get_rates
from src.exceptions import ExternalApiException, NetworkException

CACHE_CONTROL = "public, max-age=300, stale-if-error=86400"


def _service_raising(exc: Exception):
    svc = MagicMock()
    svc.fetch_rates.side_effect = exc
    return svc


# ---------------------------------------------------------------------------
# ExternalApiException handling
# ---------------------------------------------------------------------------

def test_handle_external_api_exception_returns_503():
    svc = _service_raising(ExternalApiException("HTTP 500", 500))

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert result["statusCode"] == 503


def test_handle_external_api_exception_response_is_problem_json():
    svc = _service_raising(ExternalApiException("HTTP 500", 500))

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert result["headers"]["Content-Type"] == "application/problem+json"


def test_handle_external_api_exception_body_has_correct_title():
    svc = _service_raising(ExternalApiException("HTTP 500", 500))

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert json.loads(result["body"])["title"] == "Upstream API Error"


def test_handle_external_api_exception_body_has_correct_detail():
    svc = _service_raising(ExternalApiException("HTTP 500", 500))

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert json.loads(result["body"])["detail"] == (
        "The currency rates provider returned an error. Please retry shortly."
    )


def test_handle_external_api_exception_body_has_correct_type():
    svc = _service_raising(ExternalApiException("HTTP 500", 500))

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert json.loads(result["body"])["type"] == "urn:currency-service:upstream-error"


# ---------------------------------------------------------------------------
# NetworkException handling
# ---------------------------------------------------------------------------

def test_handle_network_exception_returns_503():
    svc = _service_raising(NetworkException("unreachable"))

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert result["statusCode"] == 503


def test_handle_network_exception_response_is_problem_json():
    svc = _service_raising(NetworkException("unreachable"))

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert result["headers"]["Content-Type"] == "application/problem+json"


def test_handle_network_exception_body_has_correct_title():
    svc = _service_raising(NetworkException("unreachable"))

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert json.loads(result["body"])["title"] == "Upstream Unreachable"


def test_handle_network_exception_body_has_correct_detail():
    svc = _service_raising(NetworkException("unreachable"))

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert json.loads(result["body"])["detail"] == (
        "Unable to connect to the currency rates provider. Please retry shortly."
    )


def test_handle_network_exception_body_has_correct_type():
    svc = _service_raising(NetworkException("unreachable"))

    result = _handle_get_rates(svc, CACHE_CONTROL)

    assert json.loads(result["body"])["type"] == "urn:currency-service:network-error"
