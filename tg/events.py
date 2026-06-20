"""
tg/events.py — Обработчик входящих сообщений (userbot)
"""
import asyncio
import os
import base64
import logging
import time
import datetime
import random
from telethon import events
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji
from telethon.errors import ChannelPrivateError, ChatWriteForbiddenError

from brain.planner import should_respond
from brain.think import generate_thought
from tg.sender import send_message
from brain.style_filter import filter_response
from automation.owner_alert import alert_owner
from memory.sqlite import save_message, get_matching_sticker
from config import OWNER_ID, OWNER_NAME

logger = logging.getLogger("events")

BOT_START_TIME = time.time()
RUNNING_TASKS = {}


def get_uptime() -> str:
    return str(datetime.timedelta(seconds=int(time.time() - BOT_START_TIME)))


def get_ram_usage() -> str:
    try:
        with open(f'/proc/{os.getpid()}/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return str(int(line.split()[1]) // 1024) + ' MB'
    except Exception:
        pass
    return f"{random.randint(100, 200)} MB"


async def run_delayed_message(client, delay_seconds: int, target_chat, text: str):
    await asyncio.sleep(delay_seconds)
    try:
        await send_message(client, target_chat, text)
        logger.info(f"⏰ [Timer] Отправил в {target_chat}: {text}")
    except Exception as e:
        logger.error(f"⏰ [Timer] Ошибка: {e}")


async def execute_pending_actions(client, event, pending_actions: list):
    """Выполняет Telegram-действия после отправки основного ответа."""
    for action in pending_actions:
        name = action.get("name")
        args = action.get("args", {})
        try:
            if name == "send_message":
                username = args.get("username", "")
                text = args.get("text", "")
                if 't.me/' in username:
                    import urllib.parse
                    parsed = urllib.parse.urlparse(
                        username if username.startswith('http') else 'https://' + username
                    )
                    username = parsed.path.lstrip('/')
                    if not username.startswith('@'):
                        username = '@' + username
                    start_param = urllib.parse.parse_qs(parsed.query).get('start', [''])[0]
                    if start_param:
                        from telethon.tl.functions.messages import StartBotRequest
                        await client(StartBotRequest(bot=username, peer=username, start_param=start_param))
                        continue
                await client.send_message(username, text)
                logger.info(f"📨 [Agent] Написал {username}: {text}")

            elif name == "send_file":
                target = args.get("target") or event.chat_id
                path = args.get("path", "")
                caption = args.get("caption", "")
                if path:
                    expanded = os.path.expanduser(path)
                    await client.send_file(target, expanded, caption=caption)
                    logger.info(f"📁 [Agent] Отправил файл {path} в {target}")

            elif name == "create_poll":
                target = args.get("target") or event.chat_id
                question = args.get("question", "")
                options = args.get("options", [])
                is_anonymous = args.get("is_anonymous", True)
                is_quiz = args.get("is_quiz", False)
                correct_option_id = args.get("correct_option_id")

                from telethon.tl.types import InputMediaPoll, Poll, PollAnswer
                poll_answers = [
                    PollAnswer(text=opt, option=str(i).encode('utf-8'))
                    for i, opt in enumerate(options)
                ]
                poll_obj = Poll(
                    id=random.randint(1, 1000000000),
                    question=question,
                    answers=poll_answers,
                    closed=False,
                    public_voters=not is_anonymous,
                    multiple_choice=False,
                    quiz=is_quiz
                )
                correct_answers = None
                if is_quiz and correct_option_id is not None:
                    correct_answers = [str(correct_option_id).encode('utf-8')]
                
                poll_media = InputMediaPoll(
                    poll=poll_obj,
                    correct_answers=correct_answers
                )
                await client.send_message(target, file=poll_media)
                logger.info(f"📊 [Agent] Создал опрос '{question}' в {target}")

            elif name == "send_location":
                target = args.get("target") or event.chat_id
                lat = float(args.get("latitude", 0))
                lon = float(args.get("longitude", 0))
                from telethon.tl.types import InputMediaGeoPoint, InputGeoPoint
                await client.send_message(target, file=InputMediaGeoPoint(InputGeoPoint(lat=lat, long=lon)))
                logger.info(f"📍 [Agent] Отправил локацию ({lat}, {lon}) в {target}")

            elif name == "join_channel":
                from internet.telegram_reader import join_channel
                result = await join_channel(client, args.get("channel", ""))
                logger.info(f"➕ [Agent] {result}")

            elif name == "leave_channel":
                from internet.telegram_reader import leave_channel
                result = await leave_channel(client, args.get("channel", ""))
                logger.info(f"➖ [Agent] {result}")
                if result.startswith("✅"):
                    logger.info(f"➖ [Agent] Бот вышел из чата, остальные действия отменены")
                    return

            elif name == "click_button":
                idx = args.get("index")
                text_btn = args.get("text")
                if idx is not None and event.message.buttons:
                    flat_buttons = []
                    for row in event.message.buttons:
                        flat_buttons.extend(row)
                    if 0 <= idx < len(flat_buttons):
                        btn = flat_buttons[idx]
                        if hasattr(btn, 'url') and btn.url and 't.me/' in btn.url:
                            import urllib.parse
                            parsed = urllib.parse.urlparse(
                                btn.url if btn.url.startswith('http') else 'https://' + btn.url
                            )
                            bot_un = '@' + parsed.path.lstrip('/')
                            start_param = urllib.parse.parse_qs(parsed.query).get('start', [''])[0]
                            if bot_un and start_param:
                                from telethon.tl.functions.messages import StartBotRequest
                                await client(StartBotRequest(bot=bot_un, peer=bot_un, start_param=start_param))
                                continue
                        await btn.click()
                        logger.info(f"🖱️ [Agent] Нажал кнопку [{idx}]: '{btn.text}'")
                elif text_btn:
                    await event.message.click(text=text_btn)

            elif name == "set_timer":
                seconds = args.get("seconds", 60)
                text = args.get("text", "")
                target = args.get("target", event.chat_id)
                asyncio.create_task(run_delayed_message(client, seconds, target, text))

            elif name == "react":
                emoji = args.get("emoji", "")
                if emoji:
                    await client(SendReactionRequest(
                        peer=event.chat_id,
                        msg_id=event.message.id,
                        reaction=[ReactionEmoji(emoticon=emoji)]
                    ))

            elif name == "forward_messages":
                from_chat = args.get("from_chat")
                message_ids = args.get("message_ids", [])
                to_chat = args.get("to_chat", event.chat_id)
                if from_chat and message_ids:
                    try:
                        if isinstance(from_chat, str) and (from_chat.isdigit() or from_chat.lstrip('-').isdigit()):
                            from_chat = int(from_chat)
                        if isinstance(to_chat, str) and (to_chat.isdigit() or to_chat.lstrip('-').isdigit()):
                            to_chat = int(to_chat)
                        await client.forward_messages(to_chat, message_ids, from_chat)
                    except Exception as fe:
                        logger.error(f"Ошибка пересылки сообщений: {fe}")

            elif name == "send_sticker":
                query = args.get("query", "")
                file_id = get_matching_sticker(query)
                if file_id:
                    await client.send_file(event.chat_id, file_id)

        except Exception as e:
            logger.warning(f"⚠️ [Agent] Ошибка действия {name}: {e}")


async def ensure_static_image(file_path: str) -> str:
    """
    Проверяет файл. Если это видео (WebM) или анимация, пытается извлечь первый кадр
    с помощью ffmpeg и вернуть путь к новому JPEG-файлу.
    Если это неподдерживаемый формат (например, TGS), возвращает None.
    Иначе возвращает исходный file_path.
    """
    if not file_path or not os.path.exists(file_path):
        return file_path
        
    # Читаем первые несколько байт для определения сигнатуры
    with open(file_path, "rb") as f:
        header = f.read(4)
        
    is_webm = header == b'\x1a\x45\xdf\xa3' or file_path.lower().endswith('.webm')
    is_gzip = header.startswith(b'\x1f\x8b') or file_path.lower().endswith('.tgs')
    
    if is_webm:
        jpg_path = file_path + ".jpg"
        try:
            # Извлекаем первый кадр
            proc = await asyncio.create_subprocess_exec(
                'ffmpeg', '-y', '-i', file_path, '-vframes', '1', '-f', 'image2', jpg_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if os.path.exists(jpg_path) and os.path.getsize(jpg_path) > 0:
                os.remove(file_path)
                return jpg_path
        except Exception as e:
            logger.error(f"Ошибка конвертации WebM в JPG: {e}")
            
    elif is_gzip:
        # TGS — это Gzip-архив с Lottie JSON.
        # Пробуем извлечь первый кадр с помощью lottie_convert.py
        png_path = file_path + ".png"
        try:
            import sys
            lottie_convert = os.path.join(os.path.dirname(sys.executable), "lottie_convert.py")
            if not os.path.exists(lottie_convert):
                lottie_convert = "lottie_convert.py"
                
            proc = await asyncio.create_subprocess_exec(
                sys.executable, lottie_convert, file_path, png_path, '--frame', '1',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if os.path.exists(png_path) and os.path.getsize(png_path) > 0:
                os.remove(file_path)
                return png_path
        except Exception as e:
            logger.error(f"Ошибка конвертации TGS в PNG: {e}")
            
        if os.path.exists(file_path):
            os.remove(file_path)
        return None
        
    return file_path


async def analyze_and_save_sticker_async(client, event):
    try:
        os.makedirs("database/cache", exist_ok=True)
        file_path = await event.download_media(file="database/cache/")
        if not file_path:
            return
        
        file_path = await ensure_static_image(file_path)
        if not file_path:
            return
        
        with open(file_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode('utf-8')
        
        if os.path.exists(file_path):
            os.remove(file_path)
            
        image_url = f"data:image/jpeg;base64,{b64_data}"
        
        prompt = (
            "Ты — ИИ-аналитик стикеров. Опиши этот стикер кратко, 1-3 словами или ключевыми тегами на русском языке. "
            "Например: 'подмигивающий кот', 'смеющийся череп', 'грустный смайлик', 'сердечко'. "
            "Ответь СТРОГО одной фразой или ключевыми словами через запятую, без знаков препинания в конце и лишнего текста."
        )
        
        from llm.provider import generate_response
        description = await generate_response(prompt, is_vision=True, image_url=image_url)
        description_clean = description.strip().lower().replace(".", "").replace('"', '').replace("'", "")
        
        if description_clean:
            emoji = ""
            for attr in getattr(event.sticker, 'attributes', []):
                if hasattr(attr, 'alt') and attr.alt:
                    emoji = attr.alt
                    break
            
            final_desc = f"{description_clean}, {emoji}" if emoji else description_clean
            from memory.sqlite import save_sticker
            save_sticker(event.message.file.id, final_desc)
            logger.info(f"✨ [Sticker Collector] Автосохранение стикера с описанием от Vision: {final_desc}")
    except Exception as e:
        logger.warning(f"Ошибка при анализе стикера через Vision: {e}")


def register_handlers(client):
    @client.on(events.NewMessage())
    async def handler(event):
        try:
            # Кешируем свой ID и данные владельца
            if not hasattr(client, 'me_id'):
                me = await client.get_me()
                client.me_id = me.id
                client.me_username = getattr(me, 'username', '')
                client.me_first_name = getattr(me, 'first_name', "Claw'd")
                
                # Также кешируем username владельца
                try:
                    owner_entity = await client.get_entity(OWNER_ID)
                    client.owner_username = getattr(owner_entity, 'username', '')
                except Exception as e:
                    logger.warning(f"Could not fetch owner entity on startup: {e}")
                    client.owner_username = ''

            # Автоматический сбор (коллекционирование) стикеров с анализом через Vision
            if event.sticker:
                asyncio.create_task(analyze_and_save_sticker_async(client, event))

            msg_text = (event.message.text or "").strip()

            # ─── Юзербот-команды (перехватываем исходящие) ───────────────────
            if event.out:
                if ".ping" in msg_text.lower():
                    try:
                        start = time.perf_counter_ns()
                        ping_ms = round((time.perf_counter_ns() - start) / 10**6, 3)
                        uptime = get_uptime()
                        await event.edit(
                            f"🤖 **Claw'd**\n"
                            f"⚡ Ping: `{ping_ms}` ms\n"
                            f"🕓 Uptime: `{uptime}`",
                            parse_mode="markdown"
                        )
                        return
                    except Exception as e:
                        logger.error(f".ping error: {e}")

                elif ".info" in msg_text.lower():
                    try:
                        from host.executor import get_system_info
                        start = time.perf_counter_ns()
                        ping_ms = round((time.perf_counter_ns() - start) / 10**6, 3)
                        uptime = get_uptime()
                        ram = get_ram_usage()
                        info = await get_system_info()
                        info_text = (
                            f"<blockquote>┌\n"
                            f"├  🤖 <b>Claw'd</b>\n"
                            f"├  👤 Owner: <a href='tg://user?id={OWNER_ID}'>{OWNER_NAME}</a>\n"
                            f"└</blockquote>\n"
                            f"<blockquote>┌\n"
                            f"├  🖥 OS: {info.get('os', '?')}\n"
                            f"├  🐍 Python: {info.get('python', '?')}\n"
                            f"├  ⚡ Ping: {ping_ms} ms\n"
                            f"├  💾 RAM: {ram}\n"
                            f"├  💿 Disk: {info.get('disk', '?')}\n"
                            f"├  ⏱ Uptime: {uptime}\n"
                            f"└</blockquote>"
                        )
                        await event.delete()
                        await client.send_message(
                            event.chat_id, info_text,
                            parse_mode="html",
                            reply_to=event.reply_to_msg_id
                        )
                        return
                    except Exception as e:
                        logger.error(f".info error: {e}")

            # Игнорируем остальные исходящие (кроме Избранного)
            if event.out and event.chat_id != client.me_id:
                return

            # ─── Проверяем отвечать ли ───────────────────────────────────────
            should_resp = await should_respond(event)

            sender = await event.get_sender()
            sender_name = "Пользователь"
            if sender:
                sender_name = (
                    getattr(sender, 'first_name', None)
                    or getattr(sender, 'title', None)
                    or getattr(sender, 'username', 'Пользователь')
                )
            sender_id = sender.id if sender else 0

            chat = await event.get_chat()
            chat_title = getattr(chat, 'title', 'ЛС')
            logger.info(f"📥 [{chat_title}] {sender_name}: {msg_text[:100]}")

            # ─── Команды владельца ────────────────────────────────────────────
            if sender_id == OWNER_ID:
                if msg_text.lower().startswith("напиши "):
                    parts = msg_text.split(" ", 2)
                    if len(parts) >= 3:
                        target = parts[1]
                        text_to_send = parts[2]
                        is_valid = (
                            target.startswith('@') or target.startswith('+')
                            or target.replace('-', '', 1).isdigit()
                            or 't.me/' in target
                        )
                        if is_valid:
                            try:
                                await client.send_message(target, text_to_send)
                                await send_message(client, event.chat_id, f"✅ Написал {target}")
                            except Exception as e:
                                await send_message(client, event.chat_id, f"❌ Ошибка: {e}")
                            return

            # ─── Обработка медиа ──────────────────────────────────────────────
            image_url = None

            if event.photo or event.sticker:
                if should_resp:
                    file_path = await event.download_media(file="database/cache/")
                    if file_path:
                        file_path = await ensure_static_image(file_path)
                        if file_path:
                            with open(file_path, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode('utf-8')
                            os.remove(file_path)
                            image_url = f"data:image/jpeg;base64,{b64}"
                            caption = event.message.text or ""
                            media_type = "Фото" if event.photo else "Стикер"
                            event.message.text = f"[{media_type}] {caption}".strip()

            if event.voice:
                if should_resp:
                    file_path = await event.download_media(file="database/cache/")
                    if file_path and os.path.exists(file_path):
                        try:
                            with open(file_path, "rb") as af:
                                audio_bytes = af.read()
                            os.remove(file_path)

                            from llm.provider import transcribe_audio
                            async with client.action(event.chat_id, 'record-audio'):
                                transcription = await transcribe_audio(audio_bytes, "ogg")

                            if transcription:
                                logger.info(f"🎙️ [Voice] Расшифровано: {transcription}")
                                caption = event.message.text or ""
                                event.message.text = f"[Голосовое: {transcription}] {caption}".strip()
                            else:
                                event.message.text = "[Голосовое сообщение (не удалось расшифровать)]"
                        except Exception as e:
                            logger.error(f"[Voice] Ошибка обработки голосового: {e}")
                            event.message.text = "[Голосовое сообщение (ошибка обработки)]"

            if event.video_note:
                if should_resp:
                    file_path = await event.download_media(file="database/cache/")
                    if file_path:
                        wav_path = file_path + ".wav"
                        proc = await asyncio.create_subprocess_exec(
                            'ffmpeg', '-y', '-i', file_path, '-ar', '16000', '-ac', '1', wav_path,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        await proc.communicate()

                        if os.path.exists(wav_path):
                            with open(wav_path, "rb") as af:
                                audio_bytes = af.read()
                            os.remove(file_path)
                            os.remove(wav_path)

                            from llm.provider import transcribe_audio
                            async with client.action(event.chat_id, 'record-audio'):
                                transcription = await transcribe_audio(audio_bytes, "wav")

                            if transcription:
                                logger.info(f"🎥 [VideoNote] Расшифровано: {transcription}")
                                caption = event.message.text or ""
                                event.message.text = f"[Видеосообщение: {transcription}] {caption}".strip()
                            else:
                                event.message.text = "[Видеосообщение (не удалось расшифровать)]"
                        else:
                            if os.path.exists(file_path):
                                os.remove(file_path)

            if event.video and not event.video_note and not event.sticker:
                if should_resp:
                    try:
                        file_path = await event.download_media(file="database/cache/")
                        if file_path:
                            caption = event.message.text or ""
                            event.message.text = (
                                f"[Видеофайл: {file_path}. Используй execute_shell или get_cadres для анализа.] "
                                f"{caption}"
                            ).strip()
                    except Exception as ve:
                        logger.error(f"[Video] Ошибка скачивания: {ve}")

            if event.document and not (event.photo or event.sticker or event.voice or event.video_note or event.video):
                if should_resp:
                    try:
                        doc_name = None
                        for attr in getattr(event.document, 'attributes', []):
                            if hasattr(attr, 'file_name'):
                                doc_name = attr.file_name
                                break
                        if not doc_name:
                            doc_name = "document"
                        
                        os.makedirs("database/cache", exist_ok=True)
                        dest_path = os.path.join("database/cache", doc_name)
                        file_path = await event.download_media(file=dest_path)
                        if file_path:
                            caption = event.message.text or ""
                            event.message.text = (
                                f"[Файл: {file_path}. Ты можешь прочитать его содержимое с помощью read_file, "
                                f"или скопировать его в папку 'skills' для добавления как навык с помощью write_file если тебя просит владелец.] "
                                f"{caption}"
                            ).strip()
                    except Exception as de:
                        logger.error(f"[Document] Ошибка скачивания: {de}")

            if not should_resp:
                return

            chat_id = event.chat_id
            if chat_id in RUNNING_TASKS:
                prev_task = RUNNING_TASKS[chat_id]
                if not prev_task.done():
                    prev_task.cancel()
                    logger.info(f"🔄 [Events] Отменен предыдущий запрос для чата {chat_id}")
            RUNNING_TASKS[chat_id] = asyncio.current_task()

            from tg.state import set_action
            set_action(f"Отвечает {sender_name}")

            # Сразу заходим в сеть и читаем
            try:
                await client(UpdateStatusRequest(offline=False))
            except Exception:
                pass
            try:
                await client.send_read_acknowledge(event.chat_id, event.message)
            except (ChannelPrivateError, ChatWriteForbiddenError):
                logger.info(f"➖ [Events] Не удалось отметить прочитанным в чате {event.chat_id}: бот вышел")
                return

            # Агентный цикл
            try:
                async with client.action(event.chat_id, 'typing'):
                    response, pending_actions = await generate_thought(event, image_url=image_url)
            except (ChannelPrivateError, ChatWriteForbiddenError):
                logger.info(f"➖ [Events] Бот вышел из чата {event.chat_id}, пропускаю ответ")
                return

            if response:
                await asyncio.sleep(random.uniform(0.5, 2.0))
                reply_id = event.message.id if not event.is_private else None
                try:
                    await send_message(client, event.chat_id, response, reply_to=reply_id)
                    save_message(event.chat_id, client.me_id, f"Claw'd: {response}")
                    logger.info(f"📤 [Response]: {response[:100]}")
                except (ChannelPrivateError, ChatWriteForbiddenError):
                    logger.info(f"➖ [Events] Не удалось отправить ответ в чат {event.chat_id}: бот вышел")
                    return

            if pending_actions:
                await asyncio.sleep(0.3)
                await execute_pending_actions(client, event, pending_actions)

        except asyncio.CancelledError:
            logger.info(f"📥 Запрос для чата {event.chat_id} был отменен новым сообщением")
            raise
        except Exception as e:
            import traceback
            logger.error(f"🔥 ОШИБКА В EVENTS.PY: {e}")
            traceback.print_exc()
            await alert_owner(client, f"Ошибка в events.py: {e}")
        finally:
            from tg.state import get_action, set_action
            if "Отвечает" in get_action():
                set_action("Онлайн")
