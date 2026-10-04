"""가격 출처 레지스트리. 새 출처는 fetch(product) -> list[Offer]만 구현하면 된다."""

from __future__ import annotations

from . import coupang, elevenst, webpage
from .base import Offer, SourceError, select_offer

SOURCES = {
    "11st": elevenst.fetch,
    "coupang": coupang.fetch,
    "webpage": webpage.fetch,
}


def get_offer(product) -> Offer:
    try:
        fetch = SOURCES[product.source]
    except KeyError:
        raise SourceError(f"알 수 없는 source '{product.source}' (가능: {', '.join(SOURCES)})")
    return select_offer(product, fetch(product))


__all__ = ["Offer", "SourceError", "SOURCES", "get_offer", "select_offer"]
