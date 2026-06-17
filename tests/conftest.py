import pytest

from src.config import Config
from src.rates_cache import RatesCache
from src.currency_service import CurrencyService

UPSTREAM_BASE = "https://test-upstream.local"
UPSTREAM_PATH = "/api/v1/rates"
UPSTREAM_URL = f"{UPSTREAM_BASE}{UPSTREAM_PATH}"
TEST_API_KEY = "test-key"
TEST_SOURCE = "USD"

SAMPLE_UPSTREAM = [
    {"rate": 0.9235, "source": "USD", "target": "EUR", "time": "2026-06-09T04:33:00+0000"},
    {"rate": 0.7885, "source": "USD", "target": "GBP", "time": "2026-06-09T04:33:00+0000"},
    {"rate": 154.32, "source": "USD", "target": "JPY", "time": "2026-06-09T04:33:00+0000"},
]


@pytest.fixture
def test_config() -> Config:
    return Config(
        base_url=UPSTREAM_BASE,
        path=UPSTREAM_PATH,
        source=TEST_SOURCE,
        api_key=TEST_API_KEY,
        cache_max_age=300,
        stale_if_error=86400,
    )


@pytest.fixture
def cache() -> RatesCache:
    return RatesCache()


@pytest.fixture
def service(cache: RatesCache, test_config: Config) -> CurrencyService:
    return CurrencyService(cache=cache, config=test_config)


def make_event(method: str = "GET", path: str = "/api/rates") -> dict:
    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
            }
        },
    }
