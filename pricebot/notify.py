"""텔레그램 알림."""

from __future__ import annotations

import os

from . import http

ENV_TOKEN = "TELEGRAM_BOT_TOKEN"
ENV_CHAT = "TELEGRAM_CHAT_ID"
API = "https://api.telegram.org/bot{token}/{method}"


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    @classmethod
    def from_env(cls) -> "Telegram | None":
        token = os.environ.get(ENV_TOKEN, "").strip()
        chat = os.environ.get(ENV_CHAT, "").strip()
        return cls(token, chat) if token and chat else None

    def send(self, html_text: str) -> None:
        resp = http.post_json(
            API.format(token=self.token, method="sendMessage"),
            {"chat_id": self.chat_id, "text": html_text, "parse_mode": "HTML"},
        )
        if not resp.get("ok"):
            raise RuntimeError(f"텔레그램 전송 실패: {resp}")


def get_chat_ids(token: str) -> list[tuple[str, str]]:
    """봇에게 메시지를 보낸 대화방들의 (chat_id, 이름)."""
    resp = http.get_json(API.format(token=token, method="getUpdates"))
    found: dict[str, str] = {}
    for upd in resp.get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if "id" in chat:
            name = chat.get("title") or " ".join(
                x for x in (chat.get("first_name"), chat.get("last_name")) if x
            ) or chat.get("username", "")
            found[str(chat["id"])] = name
    return list(found.items())
