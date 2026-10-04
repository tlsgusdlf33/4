"""상품 페이지에서 가격 읽기 (JSON-LD / 메타태그 / 정규식).

API가 없는 쇼핑몰·브랜드 공식몰용. robots.txt가 막은 페이지는 읽지 않는다.
쿠팡·네이버처럼 자동 수집을 약관으로 금지하거나 봇을 차단하는 사이트에는 쓰지 말 것.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.robotparser

from .. import http
from .base import Offer, SourceError, clean_title, parse_price

_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I
)
_META_PRICE_RE = re.compile(
    r'<meta[^>]+(?:property|name|itemprop)=["\'](?:product:price:amount|og:price:amount|price)["\']'
    r'[^>]*content=["\']([^"\']+)["\']',
    re.I,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def robots_allowed(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        body, ctype = http.request(robots_url)
    except http.HttpError as e:
        # RFC 9309: 4xx(robots.txt 없음)면 허용, 5xx면 서버 상태를 모르므로 금지로 본다.
        return e.status < 500
    except OSError:
        return True
    rp.parse(http.decode(body, ctype).splitlines())
    return rp.can_fetch(http.USER_AGENT, url)


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _is_type(node: dict, name: str) -> bool:
    t = node.get("@type")
    return t == name or (isinstance(t, list) and name in t)


def _jsonld_offer(page: str) -> tuple[str, int] | None:
    for block in _JSONLD_RE.findall(page):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for node in _walk(data):
            if not _is_type(node, "Product"):
                continue
            prices = []
            for offer in _walk(node.get("offers", [])):
                for key in ("lowPrice", "price"):
                    if offer.get(key) not in (None, ""):
                        try:
                            prices.append(parse_price(offer[key]))
                        except ValueError:
                            pass
                        break
            if prices:
                return str(node.get("name", "")), min(prices)
    return None


def extract(page: str, price_regex: str = "") -> tuple[str, int]:
    """페이지 HTML → (제목, 가격). 우선순위: price_regex > JSON-LD > 메타태그."""
    m = _TITLE_RE.search(page)
    title = clean_title(m.group(1)) if m else ""

    if price_regex:
        m = re.search(price_regex, page, re.S)
        if not m:
            raise SourceError(f"price_regex가 페이지에서 매칭되지 않음: {price_regex}")
        return title, parse_price(m.group(1) if m.groups() else m.group(0))

    found = _jsonld_offer(page)
    if found:
        name, price = found
        return clean_title(name) or title, price

    m = _META_PRICE_RE.search(page)
    if m:
        return title, parse_price(m.group(1))

    raise SourceError("페이지에서 가격을 찾지 못함 (JSON-LD/메타태그 없음 → price_regex 지정 필요)")


def fetch(product) -> list[Offer]:
    if not product.url:
        raise SourceError("webpage 출처에는 url이 필요함")
    if not robots_allowed(product.url):
        raise SourceError(f"robots.txt가 수집을 허용하지 않음: {product.url}")
    body, ctype = http.request(product.url, headers={"Accept-Language": "ko-KR,ko;q=0.9"})
    title, price = extract(http.decode(body, ctype), product.price_regex)
    return [Offer(title=title or product.name, price=price, url=product.url,
                  mall=urllib.parse.urlsplit(product.url).netloc)]
