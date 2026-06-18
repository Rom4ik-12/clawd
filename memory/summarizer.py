"""
memory/summarizer.py — Суммаризация длинных диалогов
"""
import asyncio
import logging
from memory.sqlite import save_summary

logger = logging.getLogger("summarizer")


async def summarize_chat_history(chat_id: int, messages: list, sender_id: int):
    """Суммаризирует историю диалога если она стала длинной."""
    if len(messages) < 20:
        return
    try:
        context = "\n".join(messages[-20:])
        prompt = (
            f"Сделай краткое саммари диалога в 2-3 предложения. "
            f"Только ключевые факты и темы. Без воды.\n\n{context}\n\nСаммари:"
        )
        from llm.provider import generate_response
        summary = await generate_response(prompt, temperature=0.3)
        if summary:
            save_summary(chat_id, summary)
            logger.info(f"✅ Саммари сохранено для чата {chat_id}")
    except Exception as e:
        logger.warning(f"Ошибка суммаризации: {e}")
