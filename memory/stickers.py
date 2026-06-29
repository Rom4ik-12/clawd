"""
memory/stickers.py — Управление стикерами Clawd.

Поддерживает два источника стикеров:
1. Нативный индекс пака Clawd4 (database/clawd4_stickers.json).
2. Избранные (faved) стикеры аккаунта (database/faved_stickers.json).

Оба индекса строятся через Vision API и кэшируются, чтобы не обращаться
к API повторно.
"""
import os
import json
import random
import asyncio
import base64
import logging
from config import BASE_DIR

logger = logging.getLogger("stickers")

DEFAULT_CLAWD4_SET = "clawd4"
CLAWD4_INDEX_PATH = os.path.join(BASE_DIR, "database", "clawd4_stickers.json")
FAVED_INDEX_PATH = os.path.join(BASE_DIR, "database", "faved_stickers.json")


def _load_index(path):
    """Загружает индекс стикеров из JSON."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[Stickers] Не удалось загрузить индекс {path}: {e}")
        return []


def _save_index(path, index):
    """Сохраняет индекс стикеров в JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[Stickers] Не удалось сохранить индекс {path}: {e}")


def _search_in_index(index, query):
    """Ищет стикер в индексе по запросу."""
    if not query:
        return None
    query_lower = query.lower().strip()
    matched = []
    for item in index:
        tags = item.get("tags", "").lower()
        if query_lower in tags:
            matched.append(item)
            continue
        query_words = set(query_lower.split())
        tag_words = set(tags.replace(",", " ").split())
        if query_words & tag_words:
            matched.append(item)
    if matched:
        return random.choice(matched).get("file_id")
    return None


def _random_from_index(index):
    """Возвращает случайный стикер из индекса."""
    if not index:
        return None
    return random.choice(index).get("file_id")


# ─── Clawd4 ──────────────────────────────────────────────────────────────────


def has_clawd4_index() -> bool:
    """True, если индекс Clawd4 уже построен и не пуст."""
    return len(_load_index(CLAWD4_INDEX_PATH)) > 0


def get_clawd4_sticker(query: str = None) -> str | None:
    """Возвращает file_id стикера из пака Clawd4."""
    index = _load_index(CLAWD4_INDEX_PATH)
    if not index:
        return None
    if query:
        return _search_in_index(index, query)
    return _random_from_index(index)


def seed_clawd4_stickers_to_db():
    """Загружает захардкоженные описания Clawd4 из JSON в базу stickers."""
    from memory.sqlite import save_sticker

    index = _load_index(CLAWD4_INDEX_PATH)
    if not index:
        return

    count = 0
    for item in index:
        file_id = item.get("file_id")
        tags = item.get("tags", "")
        if file_id and tags:
            save_sticker(file_id, tags)
            count += 1
    logger.info(f"[Stickers] Clawd4 засеян в БД: {count} стикеров.")


async def build_clawd4_index(client, short_name: str = None):
    """Строит/перестраивает индекс пака Clawd4."""
    from telethon.tl.types import InputStickerSetShortName
    from telethon.tl.functions.messages import GetStickerSetRequest
    from telethon.tl.types import DocumentAttributeSticker
    from llm.provider import generate_response

    short_name = short_name or DEFAULT_CLAWD4_SET
    if not short_name:
        return

    logger.info(f"[Stickers] Построение индекса Clawd4 ('{short_name}')...")

    try:
        input_set = InputStickerSetShortName(short_name=short_name)
        sticker_set = await client(GetStickerSetRequest(stickerset=input_set, hash=0))
        docs = sticker_set.documents
        total = len(docs)
        if not total:
            logger.warning(f"[Stickers] Пак '{short_name}' пуст или недоступен.")
            return

        os.makedirs("database/cache", exist_ok=True)
        index = []

        for i, doc in enumerate(docs):
            try:
                file_path = await client.download_media(doc, file="database/cache/")
                if not file_path:
                    continue

                from tg.events import ensure_static_image
                file_path = await ensure_static_image(file_path)
                if not file_path:
                    continue

                ext = os.path.splitext(file_path)[1].lower()
                mime_type = "image/jpeg"
                if ext == ".png": mime_type = "image/png"
                elif ext == ".webp": mime_type = "image/webp"

                with open(file_path, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode('utf-8')
                if os.path.exists(file_path):
                    os.remove(file_path)

                image_url = f"data:{mime_type};base64,{b64_data}"
                prompt = (
                    "Ты — ИИ-аналитик стикеров. Опиши этот стикер кратко, "
                    "1-3 словами или ключевыми тегами на русском языке. "
                    "Например: 'подмигивающий кот', 'смеющийся череп', 'грустный смайлик'. "
                    "Ответь СТРОГО одной фразой или ключевыми словами через запятую, "
                    "без знаков препинания в конце и лишнего текста."
                )
                description = await generate_response(prompt, is_vision=True, image_url=image_url)
                description_clean = description.strip().lower().replace(".", "").replace('"', '').replace("'", "")

                if not description_clean:
                    continue

                emoji = ""
                for attr in getattr(doc, 'attributes', []):
                    if isinstance(attr, DocumentAttributeSticker) and attr.alt:
                        emoji = attr.alt
                        break

                tags = f"{description_clean}, {emoji}" if emoji else description_clean
                index.append({
                    "file_id": str(doc.id),
                    "tags": tags,
                    "emoji": emoji,
                })
                _save_index(CLAWD4_INDEX_PATH, index)
                logger.info(f"[Stickers] Clawd4 {i+1}/{total}: {tags}")

            except Exception as e:
                logger.error(f"[Stickers] Ошибка индексации Clawd4 {i+1}: {e}")

            if (i + 1) % 3 == 0:
                await asyncio.sleep(5)
            else:
                await asyncio.sleep(1)

        logger.info(f"[Stickers] Индекс Clawd4 '{short_name}' готов: {len(index)}/{total}.")

    except Exception as e:
        logger.error(f"[Stickers] Ошибка построения индекса Clawd4 '{short_name}': {e}")


# ─── Избранные стикеры ───────────────────────────────────────────────────────


def has_faved_index() -> bool:
    """True, если индекс избранных стикеров уже построен и не пуст."""
    return len(_load_index(FAVED_INDEX_PATH)) > 0


def get_faved_sticker(query: str = None) -> str | None:
    """Возвращает file_id стикера из избранных."""
    index = _load_index(FAVED_INDEX_PATH)
    if not index:
        return None
    if query:
        return _search_in_index(index, query)
    return _random_from_index(index)


async def sync_faved_stickers(client):
    """Синхронизирует избранные стикеры аккаунта в локальный индекс."""
    from telethon.tl.functions.messages import GetFavedStickersRequest
    from telethon.tl.types import DocumentAttributeSticker
    from llm.provider import generate_response

    logger.info("[Stickers] Синхронизация избранных стикеров...")

    try:
        faved = await client(GetFavedStickersRequest(hash=0))
        docs = getattr(faved, 'stickers', [])
        if not docs:
            logger.info("[Stickers] Избранных стикеров нет.")
            return

        os.makedirs("database/cache", exist_ok=True)
        index = _load_index(FAVED_INDEX_PATH)
        existing_ids = {item.get("file_id") for item in index}
        added = 0

        for i, doc in enumerate(docs):
            try:
                file_id = str(doc.id)
                if file_id in existing_ids:
                    continue

                file_path = await client.download_media(doc, file="database/cache/")
                if not file_path:
                    continue

                from tg.events import ensure_static_image
                file_path = await ensure_static_image(file_path)
                if not file_path:
                    continue

                ext = os.path.splitext(file_path)[1].lower()
                mime_type = "image/jpeg"
                if ext == ".png": mime_type = "image/png"
                elif ext == ".webp": mime_type = "image/webp"

                with open(file_path, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode('utf-8')
                if os.path.exists(file_path):
                    os.remove(file_path)

                image_url = f"data:{mime_type};base64,{b64_data}"
                prompt = (
                    "Ты — ИИ-аналитик стикеров. Опиши этот стикер кратко, "
                    "1-3 словами или ключевыми тегами на русском языке. "
                    "Например: 'подмигивающий кот', 'смеющийся череп', 'грустный смайлик'. "
                    "Ответь СТРОГО одной фразой или ключевыми словами через запятую, "
                    "без знаков препинания в конце и лишнего текста."
                )
                description = await generate_response(prompt, is_vision=True, image_url=image_url)
                description_clean = description.strip().lower().replace(".", "").replace('"', '').replace("'", "")

                if not description_clean:
                    continue

                emoji = ""
                for attr in getattr(doc, 'attributes', []):
                    if isinstance(attr, DocumentAttributeSticker) and attr.alt:
                        emoji = attr.alt
                        break

                tags = f"{description_clean}, {emoji}" if emoji else description_clean
                index.append({
                    "file_id": file_id,
                    "tags": tags,
                    "emoji": emoji,
                })
                existing_ids.add(file_id)
                added += 1
                _save_index(FAVED_INDEX_PATH, index)
                logger.info(f"[Stickers] Faved {i+1}/{len(docs)}: {tags}")

            except Exception as e:
                logger.error(f"[Stickers] Ошибка индексации избранного стикера {i+1}: {e}")

            if (i + 1) % 3 == 0:
                await asyncio.sleep(5)
            else:
                await asyncio.sleep(1)

        logger.info(f"[Stickers] Избранные стикеры синхронизированы. Добавлено новых: {added}.")

    except Exception as e:
        logger.error(f"[Stickers] Ошибка синхронизации избранных стикеров: {e}")


async def add_faved_sticker(client, file_id: str):
    """Добавляет стикер в избранное Telegram."""
    from telethon.tl.functions.messages import FaveStickerRequest
    from telethon.tl.types import InputDocument

    try:
        input_doc = InputDocument(id=int(file_id), access_hash=0, file_reference=b'')
        await client(FaveStickerRequest(id=input_doc, unfave=False))
        return True
    except Exception as e:
        logger.error(f"[Stickers] Ошибка добавления в избранное: {e}")
        return False


async def remove_faved_sticker(client, file_id: str):
    """Удаляет стикер из избранного Telegram."""
    from telethon.tl.functions.messages import FaveStickerRequest
    from telethon.tl.types import InputDocument

    try:
        input_doc = InputDocument(id=int(file_id), access_hash=0, file_reference=b'')
        await client(FaveStickerRequest(id=input_doc, unfave=True))
        # Удаляем и из локального индекса
        index = _load_index(FAVED_INDEX_PATH)
        index = [item for item in index if item.get("file_id") != file_id]
        _save_index(FAVED_INDEX_PATH, index)
        return True
    except Exception as e:
        logger.error(f"[Stickers] Ошибка удаления из избранного: {e}")
        return False
