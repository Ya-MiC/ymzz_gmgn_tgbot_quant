"""Disabled Telegram Bot API adapter for paper reports.

This build does not send messages, does not read a bot token from chat,
does not take over /start, and has no function that places a live order
or talks to a GMGN trading bot.
"""

from __future__ import annotations


class LiveSendDisabled(RuntimeError):
    pass


class PaperReportAdapter:
    enabled = False

    def __init__(self, owner_ids: list[int] | None = None, paper_report: str = ""):
        self.owner_ids = set(owner_ids or [])
        self.paper_report = paper_report or "沒有紙上報告。"
        self.sent_messages: list[dict] = []

    def send_message(self, chat_id: int, text: str) -> None:
        raise LiveSendDisabled(
            "本版本不發送 Telegram。沒有實盤、沒有對 GMGN 官方機器人的控制。"
        )

    def handle_update(self, update: dict) -> dict:
        message = update.get("message") or {}
        text = message.get("text") or ""
        user = message.get("from") or {}
        uid = user.get("id")
        if isinstance(text, str) and text.startswith("/start"):
            return {
                "ok": True,
                "sent": False,
                "executed_order": False,
                "reply": "紙上回測未啟用發送。/start 不會授予交易權限，也沒有實盤功能。",
            }
        if self.owner_ids and uid not in self.owner_ids:
            return {
                "ok": False,
                "sent": False,
                "executed_order": False,
                "reply": "不在擁有者允許清單。",
            }
        if isinstance(text, str) and text.startswith("/report"):
            return {
                "ok": True,
                "sent": False,
                "executed_order": False,
                "reply": self.paper_report,
            }
        return {
            "ok": True,
            "sent": False,
            "executed_order": False,
            "reply": "僅紙上報告。不下單、不連錢包、不控制 GMGN 官方機器人。",
        }
