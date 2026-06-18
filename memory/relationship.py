"""
memory/relationship.py — Отслеживание отношений с контактами
"""
import json
import os
import logging

logger = logging.getLogger("relationship")
_REL_PATH = os.path.join(os.path.dirname(__file__), "..", "database", "relationships.json")

_rel_cache = {}


def _load():
    global _rel_cache
    try:
        if os.path.exists(_REL_PATH):
            with open(_REL_PATH, "r", encoding="utf-8") as f:
                _rel_cache = json.load(f)
    except Exception:
        _rel_cache = {}


def _save():
    try:
        os.makedirs(os.path.dirname(_REL_PATH), exist_ok=True)
        with open(_REL_PATH, "w", encoding="utf-8") as f:
            json.dump(_rel_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Ошибка сохранения relationship: {e}")


def update_relationship_on_message(sender_id: int, sender_name: str, message: str):
    """Обновляет запись о контакте."""
    _load()
    key = str(sender_id)
    if key not in _rel_cache:
        _rel_cache[key] = {"name": sender_name, "messages": 0, "first_seen": None}
    _rel_cache[key]["messages"] = _rel_cache[key].get("messages", 0) + 1
    _rel_cache[key]["name"] = sender_name
    if not _rel_cache[key].get("first_seen"):
        from config import local_now
        _rel_cache[key]["first_seen"] = local_now().isoformat()
    _save()


def get_relationship_prompt_snippet(sender_id: int, sender_name: str) -> str:
    """Возвращает строку с инфой об отношениях для промпта."""
    _load()
    key = str(sender_id)
    if key not in _rel_cache:
        return ""
    rel = _rel_cache[key]
    msgs = rel.get("messages", 0)
    return f"Контакт {sender_name}: написал(а) тебе {msgs} раз(а) за всё время."
