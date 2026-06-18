"""
brain/memory.py — Построение контекста для LLM
"""
import asyncio
import logging
from memory.sqlite import get_short_memory, save_message, get_summaries, get_facts
from memory.summarizer import summarize_chat_history
from memory.relationship import update_relationship_on_message, get_relationship_prompt_snippet
from config import OWNER_ID, OWNER_NAME

logger = logging.getLogger("memory")


async def build_context(chat_id: int, sender_id: int, sender_name: str, message: str) -> str:
    """Собирает полный контекст для LLM из всех источников памяти."""

    # Обновляем отношения
    update_relationship_on_message(sender_id, sender_name, message)

    # Последние сообщения
    short = get_short_memory(chat_id, 30)

    # Запускаем суммаризацию если история длинная
    if len(short) >= 20:
        asyncio.create_task(summarize_chat_history(chat_id, short, sender_id))

    # Векторная память
    related = []
    try:
        from memory.vector import query_memory
        global_mems = await asyncio.to_thread(query_memory, message, 3, None)
        chat_mems = await asyncio.to_thread(query_memory, message, 2, chat_id)
        seen = set()
        for m in global_mems + chat_mems:
            if m not in seen:
                seen.add(m)
                related.append(m)
    except Exception as e:
        logger.debug(f"Vector skip: {e}")

    context = ""

    # Инфо о владельце (чтобы агент знал кто его хозяин)
    if sender_id == OWNER_ID:
        context += f"⭐ Это {sender_name} — твой владелец. Выполняй его указания.\n\n"

    # Отношения (для ЛС)
    if chat_id > 0 and sender_id != OWNER_ID:
        rel = get_relationship_prompt_snippet(sender_id, sender_name)
        if rel:
            context += f"{rel}\n"

    # Факты о собеседнике
    facts = get_facts(sender_id, limit=5)
    if facts:
        context += f"Что я знаю о {sender_name}:\n"
        for f in facts:
            context += f"- {f}\n"
        context += "\n"

    # Сводки прошлых разговоров
    summaries = get_summaries(chat_id, limit=2)
    if summaries:
        context += "Из прошлых разговоров:\n"
        for s in summaries:
            context += f"- {s}\n"
        context += "\n"

    # Похожие воспоминания
    if related:
        context += "Похожие моменты из памяти:\n- " + "\n- ".join(related) + "\n\n"

    # Последние сообщения
    context += "Последние сообщения:\n"
    for m in short:
        context += f"> {m}\n"

    context += f"\nСейчас пишет {sender_name}: {message}"

    # Сохраняем новое сообщение
    save_message(chat_id, sender_id, f"{sender_name}: {message}")

    # Добавляем в векторную память
    if len(message.split()) > 3:
        try:
            from memory.vector import add_memory
            await asyncio.to_thread(
                add_memory,
                f"{sender_name}: {message}",
                {"chat_id": chat_id, "sender_id": sender_id}
            )
        except Exception:
            pass

    return context
