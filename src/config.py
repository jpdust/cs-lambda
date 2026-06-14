import os
from dataclasses import dataclass, field


@dataclass
class Config:
    base_url: str = field(default_factory=lambda: os.environ.get("CURRENCY_API_BASE_URL", "https://allratestoday.com"))
    path: str = field(default_factory=lambda: os.environ.get("CURRENCY_API_PATH", "/api/v1/rates"))
    source: str = field(default_factory=lambda: os.environ.get("CURRENCY_API_SOURCE", "USD"))
    api_key: str = field(default_factory=lambda: os.environ.get("CURRENCY_API_KEY", ""))
    cache_max_age: int = field(default_factory=lambda: int(os.environ.get("CURRENCY_API_CACHE_MAX_AGE", "300")))
    stale_if_error: int = field(default_factory=lambda: int(os.environ.get("CURRENCY_API_STALE_IF_ERROR", "86400")))
