"""
internet/searxng.py — SearXNG поисковый клиент
"""
import asyncio
import logging
import httpx
from config import SEARXNG_URL

logger = logging.getLogger("searxng")

SEARCH_TIMEOUT = 10


async def search(query: str, max_results: int = 5) -> str:
    """
    Поиск через SearXNG JSON API.
    Возвращает топ-N результатов с заголовками, сниппетами и ссылками.
    """
    # Пробуем несколько публичных инстансов по очереди
    instances = [
        SEARXNG_URL,
        "https://searx.be",
        "https://search.mdosch.de",
        "https://searxng.site",
    ]
    # Убираем дубли, оставляем порядок (настроенный инстанс — первый)
    seen = set()
    ordered = []
    for url in instances:
        u = url.rstrip("/")
        if u not in seen:
            seen.add(u)
            ordered.append(u)

    last_error = None
    for base_url in ordered:
        try:
            result = await _do_search(base_url, query, max_results)
            if result:
                return result
        except Exception as e:
            last_error = e
            logger.warning(f"[SearXNG] {base_url} failed: {e}")
            continue

    # Фолбэк: DuckDuckGo HTML
    logger.warning("[SearXNG] All instances failed, falling back to DuckDuckGo")
    return await _duckduckgo_fallback(query)


async def _do_search(base_url: str, query: str, max_results: int) -> str:
    """Делает запрос к одному SearXNG инстансу."""
    params = {
        "q": query,
        "format": "json",
        "categories": "general",
        "language": "ru",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
        resp = await client.get(f"{base_url}/search", params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    if not results:
        return ""

    lines = []
    for r in results[:max_results]:
        title = r.get("title", "Без заголовка")
        url = r.get("url", "")
        snippet = r.get("content", "")
        if snippet:
            lines.append(f"🔎 **{title}**\n{snippet}\n{url}")
        else:
            lines.append(f"🔎 **{title}**\n{url}")

    return "\n\n".join(lines)


async def _duckduckgo_fallback(query: str) -> str:
    """DuckDuckGo HTML как резервный вариант."""
    try:
        from bs4 import BeautifulSoup
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9"
        }
        data = {"q": query, "kl": "ru-ru"}
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, data=data)
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for snippet_tag in soup.find_all("a", class_="result__snippet"):
            text = snippet_tag.get_text(strip=True)
            if text and len(text) > 20:
                results.append(text)
            if len(results) >= 3:
                break
        if not results:
            return "поиск ничего не дал"
        return "\n".join(results)
    except Exception as e:
        return f"ошибка поиска: {e}"
