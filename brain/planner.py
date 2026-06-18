"""
brain/planner.py — Решение отвечать или нет на сообщение
"""
import logging
import time
from config import OWNER_ID

logger = logging.getLogger("planner")

# Простой rate-limit: не отвечаем чаще чем раз в N секунд в одном чате (кроме владельца)
_last_response = {}
MIN_INTERVAL = 2  # секунды


async def should_respond(event) -> bool:
    """Возвращает True если нужно отвечать на это событие."""
    try:
        sender = await event.get_sender()
        sender_id = sender.id if sender else 0

        # Не отвечаем на свои сообщения (кроме Избранного)
        if event.out and event.chat_id != sender_id:
            return False

        # Каналы — не отвечаем (обрабатываются отдельно)
        if event.is_channel and not event.is_group:
            return False

        # Если это групповой чат (не личка)
        if not event.is_private:
            me_id = getattr(event.client, 'me_id', None)
            me_username = getattr(event.client, 'me_username', '')
            me_first_name = getattr(event.client, 'me_first_name', '')
            
            if not me_id:
                try:
                    me = await event.client.get_me()
                    me_id = me.id
                    me_username = getattr(me, 'username', '') or ''
                    me_first_name = getattr(me, 'first_name', '') or ''
                except Exception:
                    pass

            msg_text = (event.message.text or "").lower()
            
            from memory.sqlite import get_setting
            bot_trigger = get_setting("bot_trigger", "")
            
            # 1. Проверяем упоминание (по юзернейму, имени или кастомному триггеру)
            mentioned = False
            if me_username and f"@{me_username.lower()}" in msg_text:
                mentioned = True
            elif me_first_name and me_first_name.lower() in msg_text:
                mentioned = True
            elif bot_trigger:
                triggers = [t.strip().lower() for t in bot_trigger.split(",") if t.strip()]
                if any(t in msg_text for t in triggers):
                    mentioned = True
                
            # 2. Проверяем, является ли это ответом на сообщение бота
            is_reply_to_me = False
            if event.message.is_reply:
                reply_msg = await event.get_reply_message()
                if reply_msg:
                    reply_sender = await reply_msg.get_sender()
                    if reply_sender and me_id and reply_sender.id == me_id:
                        is_reply_to_me = True
                        
            if not mentioned and not is_reply_to_me:
                return False

        # Владельцу в ЛС — всегда отвечаем
        if sender_id == OWNER_ID:
            return True

        # Rate-limit
        chat_id = event.chat_id
        now = time.time()
        last = _last_response.get(chat_id, 0)
        if now - last < MIN_INTERVAL:
            logger.debug(f"Rate-limit: пропускаем ответ в {chat_id}")
            return False

        _last_response[chat_id] = now
        return True

    except Exception as e:
        logger.warning(f"should_respond error: {e}")
        return True
