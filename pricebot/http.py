"""표준 라이브러리(urllib)만 쓰는 얇은 HTTP 헬퍼."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

USER_AGENT = "pricebot/0.1 (personal price alert; +https://github.com/tlsgusdlf33/A11)"
TIMEOUT = 20


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str):
        super().__init__(f"HTTP {status} {url}: {body[:300]}")
        self.status = status
        self.body = body


def request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> tuple[bytes, str]:
    """요청을 보내고 (본문 바이트, Content-Type)을 돌려준다."""
    all_headers = {"User-Agent": USER_AGENT}
    all_headers.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=all_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise HttpError(e.code, url, body) from None


def get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    body, _ = request(url, headers=headers)
    return json.loads(body)


def post_json(url: str, payload: Any, headers: dict[str, str] | None = None) -> Any:
    all_headers = {"Content-Type": "application/json;charset=UTF-8"}
    all_headers.update(headers or {})
    body, _ = request(
        url,
        method="POST",
        headers=all_headers,
        data=json.dumps(payload).encode("utf-8"),
    )
    return json.loads(body)


def decode(body: bytes, content_type: str, default: str = "utf-8") -> str:
    """Content-Type의 charset을 존중해 디코딩한다 (11번가는 EUC-KR/CP949)."""
    charset = default
    for part in content_type.split(";"):
        part = part.strip().lower()
        if part.startswith("charset="):
            charset = part.split("=", 1)[1].strip('"')
    if charset in ("euc-kr", "ks_c_5601-1987"):
        charset = "cp949"
    return body.decode(charset, "replace")
