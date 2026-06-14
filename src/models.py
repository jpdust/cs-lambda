from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional


@dataclass
class CurrencyRatesResponse:
    success: bool
    source: str
    date: Optional[str]
    rates: Dict[str, Decimal]


@dataclass
class RatesFetchResult:
    rates: CurrencyRatesResponse
    stale: bool
