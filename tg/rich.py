import httpx
import logging
import re
from config import PANEL_BOT_TOKEN

logger = logging.getLogger("rich")

def extract_inline_buttons_http(text: str):
    buttons = []
    pattern = r'\[\[(.*?)\|(.*?)\]\]'
    
    def replacer(match):
        btn_text = match.group(1).strip()
        btn_action = match.group(2).strip()
        action_data = f"ai:{btn_action}"[:64]
        buttons.append({"text": btn_text, "callback_data": action_data})
        return ""
        
    cleaned_text = re.sub(pattern, replacer, text)
    
    reply_markup = None
    if buttons:
        reply_markup = {"inline_keyboard": [buttons]}
        
    return cleaned_text.strip(), reply_markup

async def send_rich_draft(chat_id: int, draft_id: int, markdown_text: str) -> bool:
    """Отправляет черновик (Draft) RichMessage для стриминга (действует 30 секунд)."""
    if not PANEL_BOT_TOKEN:
        return False
        
    url = f"https://api.telegram.org/bot{PANEL_BOT_TOKEN}/sendRichMessageDraft"
    cleaned_text, reply_markup = extract_inline_buttons_http(markdown_text)
    
    payload = {
        "chat_id": chat_id,
        "draft_id": draft_id,
        "rich_message": {
            "markdown": cleaned_text
        }
    }
    
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=10.0)
            if resp.status_code == 200:
                return True
            else:
                logger.warning(f"sendRichMessageDraft failed: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logger.error(f"send_rich_draft error: {e}")
            return False

async def send_rich_final(chat_id: int, markdown_text: str, reply_to: int = None):
    """Отправляет финальное RichMessage (например, с таблицами). Возвращает отправленное сообщение."""
    if not PANEL_BOT_TOKEN:
        return None
        
    url = f"https://api.telegram.org/bot{PANEL_BOT_TOKEN}/sendRichMessage"
    cleaned_text, reply_markup = extract_inline_buttons_http(markdown_text)
    
    payload = {
        "chat_id": chat_id,
        "rich_message": {
            "markdown": cleaned_text
        }
    }
    
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    if reply_to:
        payload["reply_parameters"] = {"message_id": reply_to}
        
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=10.0)
            if resp.status_code == 200:
                return resp.json().get("result")
            else:
                logger.warning(f"sendRichMessage failed: {resp.status_code} {resp.text}")
                return None
        except Exception as e:
            logger.error(f"send_rich_final error: {e}")
            return None
