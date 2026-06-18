"""
tg/sender.py — Утилита для отправки сообщений с разбивкой на части
"""
import asyncio
import logging

logger = logging.getLogger("sender")
MAX_MSG_LEN = 4096


async def send_message(client, chat_id, text: str, reply_to=None):
    """Отправляет текст, разбивая на части если > 4096 символов."""
    if not text:
        return
    parts = [text[i:i + MAX_MSG_LEN] for i in range(0, len(text), MAX_MSG_LEN)]
    for i, part in enumerate(parts):
        try:
            await client.send_message(
                chat_id, part,
                reply_to=reply_to if i == 0 else None,
                parse_mode="markdown"
            )
            if len(parts) > 1 and i < len(parts) - 1:
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"send_message error: {e}")
            # Пробуем без markdown если не прошло
            try:
                await client.send_message(chat_id, part, reply_to=reply_to if i == 0 else None)
            except Exception as e2:
                logger.error(f"send_message fallback error: {e2}")
