#!/usr/bin/env python3
"""
scripts/index_clawd4.py — Standalone-скрипт для построения индекса стикерпака Clawd4.

Запускает Telegram-бота (только для чтения стикерпака), прогоняет стикеры
через Vision API и сохраняет индекс в database/clawd4_stickers.json.
"""
import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from telethon import TelegramClient
from config import API_ID, API_HASH, PANEL_BOT_TOKEN, DEFAULT_STICKER_SET
from memory.stickers import build_clawd4_index, DEFAULT_CLAWD4_SET

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("index_clawd4")


async def main():
    if not PANEL_BOT_TOKEN:
        logger.error("PANEL_BOT_TOKEN не задан в .env")
        return
    if not API_ID or not API_HASH:
        logger.error("TG_API_ID и TG_API_HASH должны быть заданы в .env")
        return

    short_name = DEFAULT_STICKER_SET or DEFAULT_CLAWD4_SET
    logger.info(f"Подключаюсь к Telegram и индексирую пак '{short_name}'...")

    client = TelegramClient("index_clawd4_session", API_ID, API_HASH)
    await client.start(bot_token=PANEL_BOT_TOKEN)

    try:
        await build_clawd4_index(client, short_name=short_name)
        logger.info("Индексация завершена.")
    except Exception as e:
        logger.error(f"Ошибка индексации: {e}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
