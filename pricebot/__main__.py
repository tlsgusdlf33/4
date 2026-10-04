"""CLI: python -m pricebot {check,search,status,chat-id,test-alert,deeplink}"""

from __future__ import annotations

import argparse
import os
import sys

from . import checker, config as config_mod, http, notify, state as state_mod
from .checker import won
from .sources import SourceError, coupang, elevenst

DEFAULT_CONFIG = "products.toml"
DEFAULT_STATE = "state/prices.json"


def cmd_check(args) -> int:
    cfg = config_mod.load(args.config)
    st = state_mod.load(args.state)
    tg = None if args.dry_run else notify.Telegram.from_env()
    if not args.dry_run and tg is None:
        print("! TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID가 없어 알림은 화면에만 출력합니다.")

    outcomes = checker.run(cfg, st)
    send_failed = False
    for out in outcomes:
        p = out.product
        if out.error:
            print(f"[실패] {p.name}: {out.error}")
        else:
            mark = "🔔" if out.alert_price is not None else "  "
            print(f"[확인] {mark} {p.name}: {won(out.offer.price)} (목표 {won(p.target_price)})")
        for msg in out.messages:
            if tg is None:
                print("----- 알림 -----\n" + msg + "\n----------------")
                continue
            try:
                tg.send(msg)
            except Exception as e:
                send_failed = True
                print(f"[전송 실패] {p.name}: {e}")
                break
        else:
            # 텔레그램 전송까지 성공했을 때만 중복 방지값을 기록 (실패·미설정이면 다음에 다시 알림)
            if tg is not None:
                checker.mark_sent(st, out)

    if not args.dry_run:
        state_mod.save(args.state, st)

    all_failed = bool(outcomes) and all(o.error for o in outcomes)
    if all_failed:
        print("모든 상품 확인에 실패했습니다. API 키/네트워크를 확인하세요.")
    return 1 if (all_failed or send_failed) else 0


def cmd_search(args) -> int:
    fetchers = {"11st": elevenst.search, "coupang": coupang.search}
    try:
        offers = fetchers[args.source](args.query)
    except (SourceError, http.HttpError, OSError) as e:
        print(f"오류: {e}")
        return 1
    if not offers:
        print("결과 없음")
    for o in sorted(offers, key=lambda o: o.price):
        print(f"{o.price:>12,}원  code={o.product_code:<14} {o.title[:60]}  [{o.mall}]")
    print("\n원하는 상품의 code를 products.toml의 product_code에 넣으면 그 상품만 추적합니다.")
    return 0


def cmd_status(args) -> int:
    cfg = config_mod.load(args.config)
    st = state_mod.load(args.state)
    for p in cfg.products:
        e = st.get(p.id, {})
        last = won(e["last_price"]) if e.get("last_price") is not None else "-"
        low = won(e["lowest_price"]) if e.get("lowest_price") is not None else "-"
        flag = "" if p.enabled else " (꺼짐)"
        err = f"  ⚠ {e['last_error']}" if e.get("last_error") else ""
        print(f"{p.name}{flag}: 현재 {last} / 최저 {low} / 목표 {won(p.target_price)}"
              f"  ({e.get('last_checked', '미확인')}){err}")
    return 0


def cmd_chat_id(args) -> int:
    token = os.environ.get(notify.ENV_TOKEN, "").strip()
    if not token:
        print(f"환경변수 {notify.ENV_TOKEN}를 먼저 설정하세요.")
        return 1
    chats = notify.get_chat_ids(token)
    if not chats:
        print("받은 메시지가 없습니다. 텔레그램에서 봇에게 아무 메시지나 보낸 뒤 다시 실행하세요.")
        return 1
    for cid, name in chats:
        print(f"chat_id={cid}  ({name})")
    return 0


def cmd_test_alert(args) -> int:
    tg = notify.Telegram.from_env()
    if tg is None:
        print("TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID를 설정하세요.")
        return 1
    tg.send("✅ pricebot 연결 테스트: 이 메시지가 보이면 알림 설정이 끝난 것입니다.")
    print("전송 완료")
    return 0


def cmd_deeplink(args) -> int:
    try:
        links = coupang.deeplink(args.urls)
    except (SourceError, http.HttpError, OSError) as e:
        print(f"오류: {e}")
        return 1
    for orig, short in links.items():
        print(f"{orig}\n  → {short}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pricebot", description="가격 하락 알림 봇")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--state", default=DEFAULT_STATE)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="모든 상품 가격 확인 후 알림")
    p.add_argument("--dry-run", action="store_true", help="알림 전송·상태 저장 없이 결과만 출력")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("search", help="상품코드 찾기용 검색")
    p.add_argument("source", choices=["11st", "coupang"])
    p.add_argument("query")
    p.set_defaults(func=cmd_search)

    sub.add_parser("status", help="저장된 가격 기록 보기").set_defaults(func=cmd_status)
    sub.add_parser("chat-id", help="텔레그램 chat_id 확인").set_defaults(func=cmd_chat_id)
    sub.add_parser("test-alert", help="텔레그램 테스트 메시지").set_defaults(func=cmd_test_alert)

    p = sub.add_parser("deeplink", help="쿠팡 URL → 파트너스 링크 (최종 승인 후)")
    p.add_argument("urls", nargs="+")
    p.set_defaults(func=cmd_deeplink)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
