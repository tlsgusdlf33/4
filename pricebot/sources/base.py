"""가격 출처 공통 타입과 상품 선택 로직."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Product


class SourceError(RuntimeError):
    """가격을 가져오지 못했을 때 (키 없음, 결과 없음, 차단 등)."""


@dataclass
class Offer:
    title: str
    price: int
    url: str
    product_code: str = ""
    mall: str = ""
    # 출처가 이미 제휴 링크를 돌려준 경우 (예: 쿠팡 파트너스 API의 productUrl)
    affiliate_url: str = ""


_TAG_RE = re.compile(r"<[^>]+>")


def clean_title(raw: str) -> str:
    return html.unescape(_TAG_RE.sub("", raw)).strip()


def parse_price(raw: object) -> int:
    """'1,234,000원' / '1234000.00' / 1234000 → 1234000"""
    if isinstance(raw, (int, float)):
        return int(raw)
    text = str(raw).strip()
    m = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if not m:
        raise ValueError(f"가격을 읽을 수 없음: {raw!r}")
    return int(float(m.group(0).replace(",", "")))


def select_offer(product: "Product", offers: list[Offer]) -> Offer:
    """검색 결과에서 추적 대상 상품을 고른다.

    - product_code가 있으면 그 상품만 본다 (가장 정확).
    - 없으면 include 단어를 모두 포함하고 exclude 단어를 하나도 포함하지 않는
      결과 중 최저가를 고른다. 케이스·필름 같은 액세서리가 최저가로 잡히는 걸
      막으려면 exclude를 꼭 채워 두는 게 좋다.
    """
    if product.product_code:
        for o in offers:
            if o.product_code == product.product_code:
                return o
        raise SourceError(
            f"고정한 상품코드 {product.product_code}가 검색 결과에 없음 "
            "(품절·판매종료이거나 query가 바뀌었을 수 있음)"
        )

    def ok(o: Offer) -> bool:
        t = o.title.lower()
        if any(w.lower() not in t for w in product.include):
            return False
        if any(w.lower() in t for w in product.exclude):
            return False
        return o.price > 0

    candidates = [o for o in offers if ok(o)]
    if not candidates:
        raise SourceError(
            f"조건(include={product.include}, exclude={product.exclude})에 맞는 결과 없음 "
            f"(검색 결과 {len(offers)}건)"
        )
    return min(candidates, key=lambda o: o.price)
