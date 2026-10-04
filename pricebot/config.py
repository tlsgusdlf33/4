"""products.toml 로더."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# 쿠팡 파트너스가 요구하는 대가성 문구 (공정위 추천·보증 심사지침).
COUPANG_DISCLOSURE = "이 게시물은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
DEFAULT_DISCLOSURE = "※ 이 알림의 링크는 제휴 링크로, 구매 시 운영자가 수수료를 받을 수 있습니다."


@dataclass
class Product:
    id: str
    name: str
    target_price: int
    source: str
    query: str = ""
    url: str = ""
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    product_code: str = ""
    price_regex: str = ""
    affiliate_url: str = ""
    enabled: bool = True


@dataclass
class Settings:
    disclosure: str = DEFAULT_DISCLOSURE
    history_limit: int = 120


@dataclass
class Config:
    settings: Settings
    products: list[Product]


class ConfigError(ValueError):
    pass


_PRODUCT_FIELDS = set(Product.__dataclass_fields__)


def load(path: str | Path) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    settings = Settings(**raw.get("settings", {}))
    products = []
    seen = set()
    for i, p in enumerate(raw.get("products", []), 1):
        unknown = set(p) - _PRODUCT_FIELDS
        if unknown:
            raise ConfigError(f"products[{i}]: 알 수 없는 항목 {sorted(unknown)}")
        for key in ("id", "name", "target_price", "source"):
            if key not in p:
                raise ConfigError(f"products[{i}]: '{key}'가 필요함")
        if p["id"] in seen:
            raise ConfigError(f"products[{i}]: id '{p['id']}' 중복")
        seen.add(p["id"])
        p["product_code"] = str(p.get("product_code", ""))
        products.append(Product(**p))
    return Config(settings=settings, products=products)
