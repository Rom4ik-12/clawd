"""
tg/botfather.py - Автосоздание бота через @BotFather
"""
import asyncio
import re
import random
import logging

logger = logging.getLogger("botfather")

async def auto_create_panel_bot(client) -> str:
    """
    Общается с @BotFather для создания нового бота, возвращает токен.
    Если не получилось, возвращает None.
    """
    logger.info("[BotFather] Начинаю автосоздание панели...")
    
    bot_name = "Claw'd Panel"
    
    from config import PANEL_BOT_USERNAME
    if PANEL_BOT_USERNAME:
        bot_username = PANEL_BOT_USERNAME
    else:
        from memory.sqlite import get_setting
        base_username = get_setting("bot_name", "Clawd").replace("'", "").replace(" ", "")
        if not base_username:
            base_username = "Clawd"
            
        random_id = random.randint(10000, 99999)
        bot_username = f"{base_username}Panel_{random_id}_bot"

    try:
        async with client.conversation("@BotFather", timeout=15) as conv:
            await conv.send_message("/newbot")
            resp = await conv.get_response()
            if "How are we going to call it" not in resp.text:
                logger.error(f"[BotFather] Неожиданный ответ на /newbot: {resp.text}")
                return None
                
            await conv.send_message(bot_name)
            resp = await conv.get_response()
            if "choose a username" not in resp.text:
                logger.error(f"[BotFather] Неожиданный ответ на имя: {resp.text}")
                return None
                
            await conv.send_message(bot_username)
            resp = await conv.get_response()
            
            attempts = 0
            while ("already taken" in resp.text or "invalid" in resp.text) and attempts < 3:
                attempts += 1
                random_id = random.randint(10000, 99999)
                bot_username = f"{base_username}Panel_{random_id}_bot"
                await conv.send_message(bot_username)
                resp = await conv.get_response()
                
            if "Use this token to access the HTTP API" in resp.text:
                match = re.search(r"(\d+:[a-zA-Z0-9_-]+)", resp.text)
                if match:
                    token = match.group(1)
                    logger.info(f"[BotFather] Успешно создан бот @{bot_username}")
                    
                    from config import OWNER_ID
                    await client.send_message(
                        OWNER_ID, 
                        f"✅ Я автоматически создал бота для Панели Управления!\n\n"
                        f"🔗 Перейди в @{bot_username} и нажми /start, чтобы настроить меня."
                    )
                    return token
                else:
                    logger.error("[BotFather] Не удалось извлечь токен из ответа")
            else:
                logger.error(f"[BotFather] Неожиданный ответ при завершении: {resp.text}")
                
    except Exception as e:
        logger.error(f"[BotFather] Ошибка при автосоздании бота: {e}")
        
    return None
