"""
internet/telegram_reader.py — Telegram action tools (join, leave, feed, inspect)
"""
import asyncio
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.types import Channel, Chat, User


async def join_channel(client, channel_username_or_link: str) -> str:
    """Подписаться на канал или группу с авто-верификацией."""
    try:
        target = channel_username_or_link.strip()
        if target.startswith("https://t.me/"):
            target = target.replace("https://t.me/", "")

        await client(JoinChannelRequest(target))
        result = f"✅ Успешно подписался на @{target}"

        # Авто-верификация (кнопки входа)
        try:
            entity = await client.get_entity(target)
            await asyncio.sleep(2)
            messages = await client.get_messages(entity, limit=5)
            verification_keywords = [
                "я не робот", "i'm not a robot", "подтвердить", "confirm",
                "verify", "согласен", "agree", "accept", "продолжить", "continue",
                "верификация", "✅", "☑️", "✔️", "👍"
            ]
            for msg in messages:
                if not msg.reply_markup:
                    continue
                for row in msg.reply_markup.rows:
                    for btn in row.buttons:
                        btn_text = (btn.text or "").lower()
                        if any(kw in btn_text for kw in verification_keywords):
                            await msg.click(text=btn.text)
                            result += f"\n🔘 Прошёл входную проверку (нажал '{btn.text}')"
                            break
        except Exception:
            pass

        return result
    except Exception as e:
        return f"❌ Не удалось подписаться на {channel_username_or_link}: {e}"


async def leave_channel(client, channel_username_or_link: str) -> str:
    """Выйти из канала или группы."""
    try:
        target = channel_username_or_link.strip()
        if target.startswith("https://t.me/"):
            target = target.replace("https://t.me/", "")
        entity = await client.get_entity(target)
        await client(LeaveChannelRequest(entity))
        return f"✅ Вышел из @{target}"
    except Exception as e:
        return f"❌ Не удалось выйти из {channel_username_or_link}: {e}"


async def get_recent_feed(client, max_channels: int = 5, posts_per_channel: int = 2) -> str:
    """Последние посты из подписанных каналов."""
    try:
        dialogs = await client.get_dialogs(limit=100)
        channels = [d for d in dialogs if d.is_channel and not d.is_group]
        if not channels:
            return "Пока не подписан ни на один канал."

        feed_items = []
        for channel in channels[:max_channels]:
            try:
                entity = channel.entity
                username = getattr(entity, 'username', None)
                username_str = f" (@{username})" if username else ""
                messages = await client.get_messages(channel.id, limit=posts_per_channel)
                posts = []
                for msg in messages:
                    if msg.text:
                        text = msg.text[:200] + "..." if len(msg.text) > 200 else msg.text
                        posts.append(f"  - {text.strip()}")
                if posts:
                    feed_items.append(f"📣 {channel.name}{username_str}:\n" + "\n".join(posts))
            except Exception:
                continue

        return "\n\n".join(feed_items) if feed_items else "Не удалось загрузить ленту."
    except Exception as e:
        return f"Ошибка при чтении ленты: {e}"


async def inspect_profile(client, target) -> str:
    """Изучить профиль пользователя, канала или группы."""
    try:
        if isinstance(target, str):
            target = target.strip()
            if target.startswith("https://t.me/"):
                target = target.replace("https://t.me/", "")
            if target.isdigit() or (target.startswith("-") and target[1:].isdigit()):
                target = int(target)

        entity = await client.get_entity(target)
        info = []
        entity_id = entity.id

        if isinstance(entity, User):
            from telethon.tl.functions.users import GetFullUserRequest
            try:
                full = await client(GetFullUserRequest(entity))
                about = full.full_user.about or "описание отсутствует"
            except Exception:
                about = "не удалось получить"

            info.append(f"👤 **Пользователь:**")
            info.append(f"ID: `{entity_id}`")
            info.append(f"Имя: {entity.first_name or ''} {entity.last_name or ''}".strip())
            if entity.username:
                info.append(f"Юзернейм: @{entity.username}")
            info.append(f"Бот: {'Да' if entity.bot else 'Нет'}")
            info.append(f"Премиум: {'Да' if entity.premium else 'Нет'}")
            info.append(f"О себе: {about}")

        elif isinstance(entity, Channel):
            from telethon.tl.functions.channels import GetFullChannelRequest
            try:
                full = await client(GetFullChannelRequest(entity))
                about = full.full_chat.about or "описание отсутствует"
                members = full.full_chat.participants_count or 0
                linked = full.full_chat.linked_chat_id
            except Exception:
                about = "не удалось получить"
                members = "?"
                linked = None

            is_group = getattr(entity, 'megagroup', False)
            info.append(f"📣 **{'Группа' if is_group else 'Канал'}:** {entity.title}")
            info.append(f"ID: `{entity_id}`")
            if entity.username:
                info.append(f"Юзернейм: @{entity.username}")
            info.append(f"Участников: {members}")
            info.append(f"Описание: {about}")
            if linked:
                info.append(f"Привязанный чат: `{linked}`")

        return "\n".join(info)
    except Exception as e:
        return f"Не удалось изучить профиль {target}: {e}"
