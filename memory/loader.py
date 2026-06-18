"""
memory/loader.py — Загрузка данных при старте
"""
import os
import logging

logger = logging.getLogger("loader")


def load_style_examples():
    """Ничего не делаем — Clawd не притворяется человеком."""
    logger.info("✅ [Loader] Clawd ready")
