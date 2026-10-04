"""쿠팡 파트너스 Open API (상품 검색 + 딥링크).

주의: API 키는 파트너스 '최종 승인'(누적 판매금액 15만 원 이상 후 심사) 뒤에만 발급된다.
검색 API는 시간당 10회로 제한되므로 쿠팡 상품은 5개 안팎으로 유지할 것.
검색 결과의 productUrl은 이미 내 파트너스 추적 링크다.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import urllib.parse

from .. import http
from .base import Offer, SourceError, clean_title, parse_price

DOMAIN = "https://api-gateway.coupang.com"
SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
DEEPLINK_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"
ENV_ACCESS = "COUPANG_ACCESS_KEY"
ENV_SECRET = "COUPANG_SECRET_KEY"


def has_keys() -> bool:
    return bool(os.environ.get(ENV_ACCESS) and os.environ.get(ENV_SECRET))


def authorization(method: str, path: str, query: str, access_key: str, secret_key: str,
                  now: time.struct_time | None = None) -> str:
    """쿠팡 CEA HMAC-SHA256 인증 헤더."""
    signed_date = time.strftime("%y%m%dT%H%M%SZ", now or time.gmtime())
    message = signed_date + method + path + query
    signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
    return (
        f"CEA algorithm=HmacSHA256, access-key={access_key}, "
        f"signed-date={signed_date}, signature={signature}"
    )


def _keys() -> tuple[str, str]:
    if not has_keys():
        raise SourceError(
            f"환경변수 {ENV_ACCESS}/{ENV_SECRET}가 없음 "
            "(쿠팡 파트너스 최종 승인 후 발급 가능)"
        )
    return os.environ[ENV_ACCESS].strip(), os.environ[ENV_SECRET].strip()


def _check(resp: dict) -> object:
    if str(resp.get("rCode", "0")) != "0":
        raise SourceError(f"쿠팡 API 오류 {resp.get('rCode')}: {resp.get('rMessage')}")
    return resp.get("data")


def search(keyword: str, limit: int = 10) -> list[Offer]:
    access, secret = _keys()
    query = urllib.parse.urlencode({"keyword": keyword, "limit": limit})
    auth = authorization("GET", SEARCH_PATH, query, access, secret)
    data = _check(http.get_json(f"{DOMAIN}{SEARCH_PATH}?{query}", {"Authorization": auth}))
    offers = []
    for item in (data or {}).get("productData", []):
        try:
            price = parse_price(item["productPrice"])
        except (KeyError, ValueError):
            continue
        offers.append(
            Offer(
                title=clean_title(item.get("productName", "")),
                price=price,
                url=item.get("productUrl", ""),
                product_code=str(item.get("productId", "")),
                mall="쿠팡" + (" 로켓배송" if item.get("isRocket") else ""),
                affiliate_url=item.get("productUrl", ""),
            )
        )
    return offers


def deeplink(urls: list[str]) -> dict[str, str]:
    """일반 쿠팡 URL → 파트너스 단축 링크. {원본: 단축} 반환."""
    access, secret = _keys()
    auth = authorization("POST", DEEPLINK_PATH, "", access, secret)
    data = _check(http.post_json(f"{DOMAIN}{DEEPLINK_PATH}", {"coupangUrls": urls},
                                 {"Authorization": auth}))
    return {d["originalUrl"]: d.get("shortenUrl") or d.get("landingUrl") for d in data or []}


def fetch(product) -> list[Offer]:
    if not product.query:
        raise SourceError("coupang 출처에는 query가 필요함")
    return search(product.query)
