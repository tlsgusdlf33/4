"""가격 확인 → 알림 판단 → 상태 갱신."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from .config import COUPANG_DISCLOSURE, Config, Product
from .sources import Offer, SourceError, get_offer

KST = timezone(timedelta(hours=9))
ERROR_ALERT_STREAK = 3  # 연속 실패가 이 횟수에 도달하면 한 번 경고


def won(n: int) -> str:
    return f"{n:,}원"


@dataclass
class Outcome:
    product: Product
    offer: Offer | None = None
    error: str = ""
    messages: list[str] = field(default_factory=list)
    # 알림 전송에 성공했을 때만 상태에 반영할 값
    alert_price: int | None = None


def decide_alert(product: Product, price: int, entry: dict) -> bool:
    """목표가 이하이고, 같은 하락 구간에서 이미 알린 가격보다 더 내려갔을 때만 알린다.

    가격이 목표가 위로 올라가면 구간이 끝난 것으로 보고 다시 알릴 수 있게 된다.
    """
    if price > product.target_price:
        return False
    last = entry.get("last_alert_price")
    return last is None or price < last


def pick_link(product: Product, offer: Offer) -> tuple[str, bool]:
    """(링크, 제휴 링크 여부)"""
    if product.affiliate_url:
        return product.affiliate_url, True
    if offer.affiliate_url:
        return offer.affiliate_url, True
    return offer.url, False


def disclosure_for(link: str, default: str) -> str:
    return COUPANG_DISCLOSURE if "coupang.com" in link else default


def format_alert(product: Product, offer: Offer, entry: dict, disclosure: str) -> str:
    link, is_affiliate = pick_link(product, offer)
    diff = product.target_price - offer.price
    lines = [
        f"📉 <b>목표가 도달</b> · {html.escape(product.name)}",
        f"현재가 <b>{won(offer.price)}</b> (목표 {won(product.target_price)}보다 {won(diff)} 저렴)",
    ]
    prev_low = entry.get("lowest_price")
    if prev_low is not None and offer.price < prev_low:
        lines.append(f"🏆 추적 이후 최저가 갱신 (이전 최저 {won(prev_low)})")
    elif entry.get("last_price") is not None:
        lines.append(f"직전 확인가 {won(entry['last_price'])}")
    seller = f" · {html.escape(offer.mall)}" if offer.mall else ""
    lines.append(f"{html.escape(offer.title[:80])}{seller}")
    lines.append(f'<a href="{html.escape(link, quote=True)}">상품 보러 가기</a>')
    if is_affiliate:
        lines += ["", html.escape(disclosure_for(link, disclosure))]
    return "\n".join(lines)


def format_error(product: Product, error: str, streak: int) -> str:
    return (
        f"⚠️ <b>가격 확인 실패 {streak}회 연속</b> · {html.escape(product.name)}\n"
        f"{html.escape(error[:300])}\n"
        "products.toml의 query/include/exclude/product_code를 확인하세요."
    )


def run(config: Config, state: dict, *, now: datetime | None = None,
        fetch: Callable[[Product], Offer] | None = None) -> list[Outcome]:
    """모든 상품을 확인하고 state를 제자리에서 갱신한다. 보낼 메시지는 Outcome에 담긴다.

    last_alert_price는 여기서 갱신하지 않는다 — 전송 성공 후 mark_sent()로 반영해서,
    텔레그램 전송이 실패하면 다음 실행 때 다시 알리도록 한다.
    """
    now = now or datetime.now(KST)
    fetch = fetch or get_offer
    stamp = now.isoformat(timespec="minutes")
    outcomes = []

    for product in config.products:
        if not product.enabled:
            continue
        entry = state.setdefault(product.id, {})
        entry["name"] = product.name
        out = Outcome(product)
        outcomes.append(out)

        try:
            offer = fetch(product)
        except Exception as e:  # 한 상품의 실패가 나머지 확인을 막지 않도록
            out.error = str(e) if isinstance(e, SourceError) else f"{type(e).__name__}: {e}"
            entry["error_streak"] = entry.get("error_streak", 0) + 1
            entry["last_error"] = out.error
            if entry["error_streak"] == ERROR_ALERT_STREAK:
                out.messages.append(format_error(product, out.error, entry["error_streak"]))
            continue

        out.offer = offer
        if decide_alert(product, offer.price, entry):
            out.messages.append(format_alert(product, offer, entry, config.settings.disclosure))
            out.alert_price = offer.price
        if offer.price > product.target_price:
            entry["last_alert_price"] = None

        entry.update(
            last_price=offer.price,
            last_checked=stamp,
            last_title=offer.title,
            last_url=offer.url,
            product_code=offer.product_code,
            error_streak=0,
            last_error="",
        )
        if entry.get("lowest_price") is None or offer.price < entry["lowest_price"]:
            entry["lowest_price"] = offer.price
            entry["lowest_at"] = stamp
        history = entry.setdefault("history", [])
        if not history or history[-1][1] != offer.price:
            history.append([stamp, offer.price])
            del history[:-config.settings.history_limit]

    return outcomes


def mark_sent(state: dict, out: Outcome) -> None:
    if out.alert_price is not None:
        state[out.product.id]["last_alert_price"] = out.alert_price
