import logging
from decimal import Decimal

import requests
import requests.exceptions

from .config import Config
from .exceptions import ExternalApiException, NetworkException
from .models import CurrencyRatesResponse, RatesFetchResult
from .rates_cache import RatesCache

log = logging.getLogger(__name__)


class CurrencyService:
    def __init__(self, cache: RatesCache, config: Config) -> None:
        self._cache = cache
        self._config = config

    def fetch_rates(self) -> RatesFetchResult:
        log.info("Fetching currency rates from upstream API (source=%s)", self._config.source)

        try:
            response = requests.get(
                f"{self._config.base_url}{self._config.path}",
                params={"source": self._config.source},
                headers={"Authorization": f"Bearer {self._config.api_key}"},
                timeout=29,
            )

            if response.status_code >= 400:
                raise ExternalApiException(
                    f"Upstream currency API returned HTTP {response.status_code}",
                    response.status_code,
                )

            upstream = response.json()

            source = upstream[0]["source"] if upstream else self._config.source
            date = upstream[0]["time"] if upstream else None

            rates: dict[str, Decimal] = {}
            for item in upstream:
                target = item["target"]
                if target not in rates:
                    rates[target] = Decimal(str(item["rate"]))
            rates = dict(sorted(rates.items()))

            result = CurrencyRatesResponse(success=True, source=source, date=date, rates=rates)
            self._cache.store(result)
            return RatesFetchResult(rates=result, stale=False)

        except ExternalApiException:
            cached = self._cache.get()
            if cached is not None:
                log.warning("Upstream unavailable; serving stale cached rates")
                return RatesFetchResult(rates=cached, stale=True)
            raise

        except requests.exceptions.RequestException as ex:
            cached = self._cache.get()
            if cached is not None:
                log.warning("Upstream unreachable (%s); serving stale cached rates", ex)
                return RatesFetchResult(rates=cached, stale=True)
            raise NetworkException(str(ex)) from ex
