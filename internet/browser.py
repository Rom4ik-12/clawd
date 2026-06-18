"""
internet/browser.py — Интернет поиск (основной: SearXNG, fallback: DDG)
"""
from internet.searxng import search as searxng_search
import httpx
import re


async def search_internet(query: str) -> str:
    """Поиск в интернете через SearXNG."""
    return await searxng_search(query)


async def search_telegram(query: str) -> str:
    """Ищет публичные Telegram-каналы/группы по запросу."""
    try:
        search_query = f"site:t.me {query} telegram"
        results_text = await searxng_search(search_query, max_results=8)

        # Извлекаем t.me ссылки из результатов
        tg_links = re.findall(r'https?://t\.me/[A-Za-z0-9_]+', results_text)
        tg_links = list(dict.fromkeys(tg_links))  # убираем дубли

        if tg_links:
            return "\n".join(tg_links[:5])

        # Если прямых ссылок нет — возвращаем сырые результаты
        if results_text and "ошибка" not in results_text.lower():
            return results_text

        return "не нашёл подходящих Telegram-чатов по запросу"
    except Exception as e:
        return f"ошибка поиска Telegram: {e}"
