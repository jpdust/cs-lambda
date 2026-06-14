"""AWS Lambda entry point for the currency rates service.

The module-level singletons (config, cache, service) are initialized once on cold start
and reused across all warm invocations — mirroring the static handler pattern in the
original Spring Boot StreamLambdaHandler.
"""

import json
import logging

from src.config import Config
from src.currency_service import CurrencyService
from src.exceptions import ExternalApiException, NetworkException
from src.rates_cache import RatesCache

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_config = Config()
_cache = RatesCache()
_service = CurrencyService(cache=_cache, config=_config)
_cache_control = f"public, max-age={_config.cache_max_age}, stale-if-error={_config.stale_if_error}"


def lambda_handler(event: dict, context) -> dict:
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "")
    path = event.get("rawPath", "")

    if method == "GET" and path == "/api/rates":
        return _handle_get_rates(_service, _cache_control)

    return {
        "statusCode": 404,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": "Not found"}),
    }


def _handle_get_rates(service: CurrencyService, cache_control: str) -> dict:
    try:
        result = service.fetch_rates()

        body = {
            "success": result.rates.success,
            "source": result.rates.source,
            "date": result.rates.date,
            "rates": {k: float(v) for k, v in result.rates.rates.items()},
        }

        headers = {
            "Content-Type": "application/json",
            "Cache-Control": cache_control,
        }
        if result.stale:
            headers["X-Rates-Stale"] = "true"

        return {"statusCode": 200, "headers": headers, "body": json.dumps(body)}

    except ExternalApiException as ex:
        log.error("Upstream currency API error (HTTP %s): %s", ex.status_code, ex)
        return _problem_response(
            "urn:currency-service:upstream-error",
            "Upstream API Error",
            "The currency rates provider returned an error. Please retry shortly.",
        )

    except NetworkException as ex:
        log.error("Network error reaching currency API: %s", ex)
        return _problem_response(
            "urn:currency-service:network-error",
            "Upstream Unreachable",
            "Unable to connect to the currency rates provider. Please retry shortly.",
        )


def _problem_response(type_uri: str, title: str, detail: str) -> dict:
    return {
        "statusCode": 503,
        "headers": {"Content-Type": "application/problem+json"},
        "body": json.dumps({"type": type_uri, "title": title, "status": 503, "detail": detail}),
    }
