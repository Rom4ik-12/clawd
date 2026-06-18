"""
automation/owner_alert.py — Алерты владельцу
"""
import logging
from config import OWNER_ID

logger = logging.getLogger("alert")

_alert_bot = None


def set_alert_bot(bot_client):
    global _alert_bot
    _alert_bot = bot_client


async def alert_owner(client, message: str):
    """Отправляет алерт владельцу: сначала через бот-панель, потом через юзербот."""
    if not OWNER_ID:
        return
    try:
        if _alert_bot:
            await _alert_bot.send_message(OWNER_ID, f"⚠️ **Clawd Alert:**\n{message}")
        else:
            await client.send_message(OWNER_ID, f"⚠️ **Clawd Alert:**\n{message}")
    except Exception as e:
        logger.error(f"Не удалось отправить алерт: {e}")
