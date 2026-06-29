"""
tg/client.py — Telethon userbot клиент
"""
from telethon import TelegramClient
from config import API_ID, API_HASH, SESSION_NAME

_client = None


def get_client() -> TelegramClient:
    global _client
    if _client is None:
        _client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    return _client


def set_client(client: TelegramClient):
    global _client
    _client = client
