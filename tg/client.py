"""
tg/client.py — Telethon userbot клиент
"""
from telethon import TelegramClient
from config import API_ID, API_HASH, SESSION_NAME

_client = None
_bot_client = None

def get_client() -> TelegramClient:
    """Возвращает юзербот клиента (или бота, если мы в ONLY_BOT_MODE)"""
    global _client
    if _client is None:
        _client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    return _client

def set_client(client: TelegramClient):
    global _client
    _client = client

def get_bot_client() -> TelegramClient:
    """Возвращает бот-клиента"""
    global _bot_client
    return _bot_client

def set_bot_client(client: TelegramClient):
    global _bot_client
    _bot_client = client

