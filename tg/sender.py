"""
tg/sender.py — Утилита для отправки сообщений с разбивкой на части
"""
import asyncio
import logging
import re
from telethon import Button
from tg.markdown import md_to_html

logger = logging.getLogger("sender")
MAX_MSG_LEN = 4096

def extract_inline_buttons(text: str):
    buttons = []
    pattern = r'\[\[(.*?)\|(.*?)\]\]'
    def replacer(match):
        btn_text = match.group(1).strip()
        btn_action = match.group(2).strip()
        action_data = f"ai:{btn_action}".encode('utf-8')[:64]
        buttons.append(Button.inline(btn_text, action_data))
        return ""
    
    cleaned_text = re.sub(pattern, replacer, text)
    return cleaned_text.strip(), buttons

async def send_message(client, chat_id, text: str, reply_to=None):
    """Отправляет текст, разбивая на части если > 4096 символов."""
    if not text:
        return
        
    text, buttons = extract_inline_buttons(text)
    html_text = md_to_html(text)
    
    parts = [html_text[i:i + MAX_MSG_LEN] for i in range(0, len(html_text), MAX_MSG_LEN)]
    
    first_msg = None
    for i, part in enumerate(parts):
        btns = buttons if i == len(parts) - 1 and buttons else None
        try:
            sent = await client.send_message(
                chat_id, part,
                reply_to=reply_to if i == 0 else None,
                parse_mode="html",
                buttons=btns
            )
            if i == 0:
                first_msg = sent
            if len(parts) > 1 and i < len(parts) - 1:
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"send_message error: {e}")
            # Пробуем без html (или если кнопки не поддерживаются - бот может быть не админом)
            try:
                await client.send_message(chat_id, part, reply_to=reply_to if i == 0 else None)
            except Exception as e2:
                logger.error(f"send_message fallback error: {e2}")
    
    return first_msg
