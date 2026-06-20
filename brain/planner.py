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


async def _get_reply_msg(event):
    """Безопасно получает reply-сообщение (Telethon иногда возвращает TotalList)."""
    reply_msg = await event.get_reply_message()
    if isinstance(reply_msg, (list, tuple)) and reply_msg:
        return reply_msg[0]
    return reply_msg


async def decide_with_llm(event, sender_name: str, me_name: str) -> bool:
    """Запрашивает быстрое решение у LLM, нужно ли отвечать на сообщение."""
    try:
        from memory.sqlite import get_short_memory
        from llm.provider import generate_response
        
        chat_id = event.chat_id
        history = get_short_memory(chat_id, limit=15)
        
        # Получаем информацию о реплае на сообщение
        reply_to_str = ""
        if event.message.is_reply:
            reply_msg = await _get_reply_msg(event)
            if reply_msg:
                reply_sender = await reply_msg.get_sender()
                if reply_sender:
                    reply_sender_name = (
                        getattr(reply_sender, 'first_name', None)
                        or getattr(reply_sender, 'username', None)
                        or 'другого пользователя'
                    )
                    reply_to_str = f" (в ответ на сообщение от {reply_sender_name})"
        
        # Добавляем текущее сообщение, так как в БД его еще нет
        current_msg = f"{sender_name}{reply_to_str}: {event.message.text or ''}"
        history.append(current_msg)
        
        history_str = "\n".join(history)
        
        prompt = f"""Ты — ИИ-ассистент по имени {me_name}. Ты анализируешь диалог в Telegram-чате, чтобы решить, нужно ли тебе ответить на ПОСЛЕДНЕЕ сообщение.

Последние сообщения в чате (предыдущие сообщения):
{history_str}

Правила решения:
Ответь YES, только если выполняется хотя бы одно из условий:
1. Последнее сообщение явно и недвусмысленно обращено к тебе (по твоему имени {me_name}, твоему юзернейму, или по контексту понятно, что обращаются именно к тебе, например: "бот, сделай...", "Claw'd, как дела?").
2. Последнее сообщение является прямым ответом (reply) на твое сообщение (от Claw'd/Clawd) и продолжает диалог с тобой.
3. Тебе задают вопрос, просят что-то сделать, или ожидает твоего ответа/реакции именно от тебя как от ИИ.

Ответь NO, если:
1. Это сообщение является ответом (reply) на сообщение другого пользователя (не тебя).
2. Это сообщение обращено к другому участнику чата или является общим высказыванием/вопросом ко всей группе ("кто знает...", "всем привет" и т.д.).
3. Последнее сообщение — это просто реплика, не требующая твоего ответа ("да", "ок", "хорошо", смайлики и т.д.), или если диалог с тобой завершен.
4. У тебя есть сомнения, обращено ли сообщение к тебе. Всегда лучше промолчать (NO), чем вклиниться в чужой разговор.

Ответь СТРОГО одним словом: YES или NO."""
        
        decision = await generate_response(prompt, temperature=0.0)
        decision_clean = decision.strip().upper()
        
        logger.info(f"🤔 [Planner] Решение ИИ для {sender_name}: {decision_clean}")
        return "YES" in decision_clean
    except Exception as e:
        logger.error(f"Ошибка в decide_with_llm: {e}")
        return True


async def should_respond(event) -> bool:
    """Возвращает True если нужно отвечать на это событие."""
    try:
        sender = await event.get_sender()
        sender_id = sender.id if sender else 0

        # Свой ID бота
        me_id = getattr(event.client, 'me_id', None)
        me_username = getattr(event.client, 'me_username', '')
        me_first_name = getattr(event.client, 'me_first_name', "Claw'd")

        if not me_id:
            try:
                me = await event.client.get_me()
                me_id = me.id
                event.client.me_id = me_id
                me_username = getattr(me, 'username', '') or ''
                event.client.me_username = me_username
                me_first_name = getattr(me, 'first_name', '') or "Claw'd"
                event.client.me_first_name = me_first_name
            except Exception:
                pass

        # Не отвечаем на свои сообщения (кроме Избранного — где chat_id == me_id)
        if event.out and event.chat_id != me_id:
            return False

        # Каналы — не отвечаем (обрабатываются отдельно)
        if event.is_channel and not event.is_group:
            return False

        # Владельцу в ЛС — всегда отвечаем без раздумий
        if event.is_private and sender_id == OWNER_ID:
            return True

        sender_name = "Пользователь"
        if sender:
            sender_name = (
                getattr(sender, 'first_name', None)
                or getattr(sender, 'title', None)
                or getattr(sender, 'username', 'Пользователь')
            )

        # Проверяем явное упоминание
        import re
        msg_text = (event.message.text or "").lower()
        from memory.sqlite import get_setting
        bot_trigger = get_setting("bot_trigger", "")

        mentioned = False

        # 1. Точное совпадение @username
        if me_username and f"@{me_username.lower()}" in msg_text:
            mentioned = True

        # 2. Username без @ как отдельное слово (например «xclawd» без собачки)
        if not mentioned and me_username:
            if re.search(r'\b' + re.escape(me_username.lower()) + r'\b', msg_text):
                mentioned = True

        # 3. Если в сообщении есть любой @упоминание — это не нам,
        #    только если наш юзернейм уже не найден выше
        if not mentioned and re.search(r'@\w+', msg_text):
            mentioned = False  # Кто-то другой упомянут, не мы

        # 4. Имя бота как отдельное слово (word boundary, не подстрока)
        #    Ищем и оригинальное имя, и без апострофа (Claw'd → clawd)
        if not mentioned and me_first_name:
            name_variants = {me_first_name.lower()}
            # Вариант без апострофа и спецсимволов
            name_clean = re.sub(r"[^a-zа-яё0-9]", "", me_first_name.lower())
            if name_clean:
                name_variants.add(name_clean)
            for name_var in name_variants:
                if re.search(r'(?<![\w@])' + re.escape(name_var) + r'(?![\w])', msg_text):
                    mentioned = True
                    break

        # 5. Кастомные триггеры (тоже по границам слова)
        if not mentioned and bot_trigger:
            triggers = [t.strip().lower() for t in bot_trigger.split(",") if t.strip()]
            if any(re.search(r'\b' + re.escape(t) + r'\b', msg_text) for t in triggers):
                mentioned = True

        # Проверяем ответ на наше сообщение
        is_reply_to_me = False
        if event.message.is_reply:
            reply_msg = await _get_reply_msg(event)
            if reply_msg:
                reply_sender = await reply_msg.get_sender()
                if reply_sender and me_id and reply_sender.id == me_id:
                    is_reply_to_me = True

        # Если это групповой чат
        if not event.is_private:
            # Если это ответ кому-то другому (не нам) и нас не упомянули — точно игнорируем
            if event.message.is_reply and not is_reply_to_me and not mentioned:
                return False

            # Если упомянули или ответили нам — реагируем
            if mentioned or is_reply_to_me:
                pass
            # Иначе, если включено динамическое решение, даем решить LLM
            elif get_setting("dynamic_decide", "True") == "True":
                need_resp = await decide_with_llm(event, sender_name, me_first_name)
                if not need_resp:
                    return False
            else:
                return False
        else:
            # В личных сообщениях (не от владельца)
            if get_setting("dynamic_decide", "True") == "True":
                need_resp = await decide_with_llm(event, sender_name, me_first_name)
                if not need_resp:
                    return False

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
