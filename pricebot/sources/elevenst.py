"""11번가 Open API 상품검색 (https://openapi.11st.co.kr).

무료이며 키당 서비스별 하루 5,000회 호출 제한이 있다. 응답은 EUC-KR XML이다.
"""

from __future__ import annotations

import os
import re
import urllib.parse
import xml.etree.ElementTree as ET

from .. import http
from .base import Offer, SourceError, clean_title, parse_price

ENDPOINT = "https://openapi.11st.co.kr/openapi/OpenApiService.tmall"
ENV_KEY = "ELEVENST_API_KEY"


def search(keyword: str, page_size: int = 50) -> list[Offer]:
    key = os.environ.get(ENV_KEY, "").strip()
    if not key:
        raise SourceError(f"환경변수 {ENV_KEY}가 없음 (11번가 OPENAPI CENTER에서 발급)")
    # 문서에 검색어 인코딩이 명시돼 있지 않아 UTF-8로 먼저 보내고,
    # 한글 검색어인데 결과가 0건이면 EUC-KR(CP949)로 한 번 더 시도한다.
    encodings = ["utf-8"] if keyword.isascii() else ["utf-8", "cp949"]
    offers: list[Offer] = []
    for enc in encodings:
        params = {
            "key": key,
            "apiCode": "ProductSearch",
            "keyword": keyword.encode(enc, "replace"),
            "pageNum": "1",
            "pageSize": str(page_size),
            "sortCd": "L",  # 낮은가격순
        }
        body, ctype = http.request(f"{ENDPOINT}?{urllib.parse.urlencode(params)}")
        offers = parse(http.decode(body, ctype, default="cp949"))
        if offers:
            break
    return offers


def parse(xml_text: str) -> list[Offer]:
    # expat은 EUC-KR 같은 멀티바이트 선언을 못 읽으므로 디코딩한 뒤 선언을 떼고 파싱한다.
    xml_text = re.sub(r"^\s*<\?xml[^>]*\?>", "", xml_text)
    root = ET.fromstring(xml_text)

    if root.tag == "ErrorResponse":
        msg = root.findtext("ErrorDetail") or root.findtext("ErrorMessage") or "알 수 없는 오류"
        raise SourceError(f"11번가 API 오류 {root.findtext('ErrorCode')}: {msg.strip()}")

    offers = []
    for p in root.iter("Product"):
        code = (p.findtext("ProductCode") or "").strip()
        raw_price = p.findtext("SalePrice") or p.findtext("ProductPrice")
        if not code or not raw_price:
            continue
        try:
            price = parse_price(raw_price)
        except ValueError:
            continue
        url = (p.findtext("DetailPageUrl") or "").strip() or f"https://www.11st.co.kr/products/{code}"
        offers.append(
            Offer(
                title=clean_title(p.findtext("ProductName") or ""),
                price=price,
                url=url,
                product_code=code,
                mall=(p.findtext("Seller") or "11번가").strip(),
            )
        )
    return offers


def fetch(product) -> list[Offer]:
    if not product.query:
        raise SourceError("11st 출처에는 query가 필요함")
    return search(product.query)
