import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"

import asyncio
import logging
from tg.client import get_client
from tg.events import register_handlers
from memory.sqlite import init_db
from memory.loader import load_style_examples
from automation.scheduler import background_routine

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/clawd.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Глушим надоедливые логи
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
logging.getLogger("telethon").setLevel(logging.WARNING)


async def sync_missed_messages(client):
    """Синхронизирует сообщения пришедшие пока бот был оффлайн."""
    print("🔄 [Sync] Проверка пропущенных сообщений...")
    try:
        dialogs = await client.get_dialogs(limit=20)
        me = await client.get_me()
        me_id = me.id

        from memory.sqlite import get_short_memory, save_message

        for dialog in dialogs:
            chat_id = dialog.id
            if not (dialog.is_user or dialog.is_group):
                continue

            tg_msgs = await client.get_messages(chat_id, limit=15)
            if not tg_msgs:
                continue

            db_msgs = get_short_memory(chat_id, limit=20)
            to_save = []

            for msg in reversed(tg_msgs):
                if not msg.text:
                    continue

                if msg.sender_id == me_id:
                    sender_name = "Claw'd"
                else:
                    sender = await msg.get_sender()
                    sender_name = (
                        getattr(sender, 'first_name', None)
                        or getattr(sender, 'username', 'чел')
                        if sender else 'чел'
                    )

                expected_text = f"{sender_name}: {msg.text}"
                found = any(db_m.strip() == expected_text.strip() for db_m in db_msgs)

                if not found:
                    to_save.append((msg.sender_id, expected_text))

            for sender_id, text in to_save:
                save_message(chat_id, sender_id, text)
                print(f"📥 [Sync] Добавлено: {text[:60]}")

        print("✅ [Sync] Синхронизация завершена")
    except Exception as e:
        print(f"❌ [Sync] Ошибка: {e}")

async def sync_avatar_description(client):
    """Единожды загружает аватарку бота и просит Vision сгенерировать её описание для системного промпта."""
    from memory.sqlite import get_setting, set_setting
    if get_setting("bot_avatar", ""):
        return
        
    try:
        print("🖼️ [Sync] Генерирую описание аватарки...")
        me = await client.get_me()
        photo_file = await client.download_profile_photo(me, file="database/cache/")
        
        if not photo_file:
            set_setting("bot_avatar", "Аватарка отсутствует")
            return
            
        import os, base64
        ext = os.path.splitext(photo_file)[1].lower()
        mime_type = "image/jpeg"
        if ext == ".png": mime_type = "image/png"
        elif ext == ".webp": mime_type = "image/webp"

        with open(photo_file, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode('utf-8')
        os.remove(photo_file)
            
        image_url = f"data:{mime_type};base64,{b64_data}"
        
        prompt = (
            "Опиши что изображено на этой аватарке кратко, в 3-5 словах. "
            "Например: 'оранжевый пиксельный пришелец', 'грустный кот', 'фото парня в очках'. "
            "Отвечай только описанием, без лишних слов и точек."
        )
        
        from llm.provider import generate_response
        description = await generate_response(prompt, is_vision=True, image_url=image_url)
        
        if description:
            set_setting("bot_avatar", description.strip())
            print(f"✅ [Sync] Описание аватарки сохранено: {description.strip()}")
    except Exception as e:
        print(f"❌ [Sync] Ошибка генерации аватарки: {e}")


async def main():
    # Инициализация
    init_db()
    load_style_examples()

    client = get_client()
    await client.start()
    print("🤖 Clawd is online!")

    # Регистрация обработчиков userbot
    register_handlers(client)

    # Панель управления (бот)
    from config import PANEL_BOT_TOKEN
    from tg.panel import init_panel_bot
    
    if not PANEL_BOT_TOKEN:
        from tg.botfather import auto_create_panel_bot
        token = await auto_create_panel_bot(client)
        if token:
            import os
            env_path = os.path.join(os.path.dirname(__file__), ".env")
            with open(env_path, "a") as f:
                f.write(f"\nPANEL_BOT_TOKEN={token}\n")
            init_panel_bot(client, token=token)
    else:
        init_panel_bot(client)

    # Синхронизация пропущенных сообщений
    asyncio.create_task(sync_missed_messages(client))

    # Разовое чтение аватарки (если еще не прочитана)
    asyncio.create_task(sync_avatar_description(client))

    # Фоновые задачи
    asyncio.create_task(background_routine())

    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен (Ctrl+C).")
