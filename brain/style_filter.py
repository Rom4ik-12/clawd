"""
brain/style_filter.py — Постобработка ответов
"""
import re
import logging

logger = logging.getLogger("style_filter")


def filter_response(text: str, last_msg: str = None) -> str:
    """
    Базовая постобработка ответа:
    - Убирает лишние служебные артефакты
    - Обрезает слишком длинные ответы
    - Убирает дублирование предыдущего ответа
    """
    if not text:
        return text

    # Убираем эмодзи и текстовые смайлы
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[:=;]-[)D(O/|\\Pdp*]|[:=;][)D(O/|\\Pdp*]', '', text)

    # Убираем артефакты markdown которые не нужны в TG
    # (оставляем **bold** и _italic_ — TG их поддерживает)
    text = text.strip()

    # Убираем ``` блоки только если это не код
    # (но оставляем если реально код — агент может выводить результаты команд)

    # Если ответ слишком длинный — обрезаем
    MAX_LENGTH = 4096
    if len(text) > MAX_LENGTH:
        text = text[:MAX_LENGTH - 3] + "..."

    # Дублирование предыдущего ответа
    if last_msg and text.strip() == last_msg.strip():
        return ""

    return text
