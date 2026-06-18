"""
brain/think.py — Агентный цикл Clawd
Поддерживает: поиск SearXNG, хостовые команды, Telegram-действия
"""
import json
import logging
from llm.provider import generate_with_tools, generate_response
from llm.prompts import get_chat_prompt
from llm.tools import AGENT_TOOLS, execute_local_tool
from brain.style_filter import filter_response
from brain.memory import build_context
from memory.sqlite import get_short_memory, log_shell
from automation.owner_alert import alert_owner

logger = logging.getLogger("think")

MAX_AGENT_STEPS = 10
_owner_current_name = None


async def generate_thought(event, image_url: str = None):
    """
    Основная функция генерации ответа.
    Запускает Agent Loop: модель → tool_call → выполнение → модель → ...
    Возвращает: (text_response, pending_actions)
    """
    global _owner_current_name
    message = event.message.text or "(пустое сообщение)"
    sender = await event.get_sender()
    is_bot = getattr(sender, 'bot', False) if sender else False

    sender_name = "Пользователь"
    if sender:
        sender_name = (
            getattr(sender, 'first_name', None)
            or getattr(sender, 'title', None)
            or getattr(sender, 'username', 'Пользователь')
        )
    chat_id = event.chat_id
    sender_id = sender.id if sender else 0

    from config import OWNER_ID
    
    # Инициализируем имя владельца если не задано
    if not _owner_current_name:
        if hasattr(event.client, 'owner_username') and event.client.owner_username:
            _owner_current_name = f"@{event.client.owner_username}"
        else:
            try:
                owner_entity = await event.client.get_entity(OWNER_ID)
                owner_un = getattr(owner_entity, 'username', None)
                if owner_un:
                    _owner_current_name = f"@{owner_un}"
                    event.client.owner_username = owner_un
                else:
                    owner_first = getattr(owner_entity, 'first_name', None)
                    if owner_first:
                        _owner_current_name = owner_first
            except Exception as e:
                logger.warning(f"Could not fetch owner entity: {e}")

    if sender_id == OWNER_ID:
        owner_un = getattr(sender, 'username', None)
        if owner_un:
            sender_name = f"@{owner_un}"
            _owner_current_name = f"@{owner_un}"
            if hasattr(event.client, 'owner_username'):
                event.client.owner_username = owner_un
        else:
            _owner_current_name = sender_name

    owner_name = _owner_current_name or "Владелец"

    # Строим контекст
    context = await build_context(chat_id, sender_id, sender_name, message)

    if is_bot:
        context += (
            "\n\n[ВАЖНО]: Твой собеседник — БОТ. Нажимай его кнопки (click_button) если они есть. "
            "Текст отправляй только если бот явно просит ввести данные."
        )

    # Кнопки в сообщении
    buttons_info = []
    if event.message.buttons:
        idx = 0
        for row in event.message.buttons:
            for btn in row:
                buttons_info.append(f"Индекс {idx}: '{btn.text}'")
                idx += 1
    if buttons_info:
        context += (
            "\n\n[КНОПКИ В ЭТОМ СООБЩЕНИИ]:\n- " +
            "\n- ".join(buttons_info) +
            "\n\nЕсли нужно нажать кнопку — используй click_button."
        )

    # Последний ответ агента (для фильтра повторов)
    last_bot_msg = None
    try:
        short = get_short_memory(chat_id, 10)
        for msg in reversed(short):
            if msg.startswith("Clawd:") or msg.startswith("Claw'd:") or msg.startswith("Бот:"):
                last_bot_msg = msg.split(":", 1)[1].strip()
                break
    except Exception:
        pass

    # Если фото/стикер — используем vision напрямую
    if image_url:
        try:
            prompt = get_chat_prompt(context, owner_name=owner_name)
            final_text = await generate_response(prompt, is_vision=True, image_url=image_url)
            filtered = filter_response(final_text, last_msg=last_bot_msg)
            return filtered, []
        except Exception as e:
            logger.warning(f"Vision error: {e}")
            return "не могу загрузить изображение прямо сейчас", []

    # ─── Агентный цикл ───────────────────────────────────────────────────────
    system_prompt = get_chat_prompt(context, owner_name=owner_name)
    messages = [{"role": "user", "content": system_prompt}]

    pending_actions = []
    final_text = None

    try:
        for step in range(MAX_AGENT_STEPS):
            text, tool_calls = await generate_with_tools(messages, AGENT_TOOLS)

            if tool_calls is None:
                final_text = text
                break

            # Добавляем ответ модели с tool_calls
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in tool_calls
                ]
            })

            # Выполняем каждый инструмент
            for tc in tool_calls:
                func_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}

                logger.info(f"🔧 [Agent] {func_name}({args})")

                # Локальные инструменты
                local_result = execute_local_tool(func_name, args)
                if local_result is not None:
                    tool_result = local_result

                # ── Поиск ────────────────────────────────────────────────────
                elif func_name == "search_web":
                    from internet.searxng import search as searxng_search
                    try:
                        tool_result = await searxng_search(args.get("query", ""))
                    except Exception as e:
                        tool_result = f"ошибка поиска: {e}"

                # ── Хостовые инструменты ─────────────────────────────────────
                elif func_name == "execute_shell":
                    from host.executor import execute_shell, format_shell_result
                    cmd = args.get("command", "")
                    timeout = args.get("timeout", 30)
                    result = await execute_shell(cmd, timeout=timeout)
                    tool_result = format_shell_result(result)
                    log_shell(cmd, tool_result, result.get("returncode", -1))

                elif func_name == "read_file":
                    from host.executor import read_file
                    tool_result = await read_file(args.get("path", ""))

                elif func_name == "write_file":
                    from host.executor import write_file
                    tool_result = await write_file(
                        args.get("path", ""),
                        args.get("content", ""),
                        args.get("append", False)
                    )

                elif func_name == "list_directory":
                    from host.executor import list_directory
                    tool_result = await list_directory(args.get("path", "."))

                elif func_name == "get_system_info":
                    from host.executor import get_system_info, format_system_info
                    info = await get_system_info()
                    tool_result = format_system_info(info)

                elif func_name == "download_file":
                    from host.executor import download_file
                    tool_result = await download_file(
                        args.get("url", ""),
                        args.get("dest", None)
                    )

                # ── Telegram инструменты (выполняемые сразу) ─────────────────
                elif func_name == "read_feed":
                    from internet.telegram_reader import get_recent_feed
                    try:
                        tool_result = await get_recent_feed(event.client)
                    except Exception as e:
                        tool_result = f"ошибка чтения ленты: {e}"

                elif func_name == "inspect_profile":
                    from internet.telegram_reader import inspect_profile
                    try:
                        tool_result = await inspect_profile(event.client, args.get("target", ""))
                    except Exception as e:
                        tool_result = f"ошибка: {e}"

                elif func_name == "read_chat_messages":
                    chat = args.get("chat", "")
                    limit = args.get("limit", 10)
                    try:
                        target = chat.strip().replace("https://t.me/", "")
                        entity = await event.client.get_entity(target)
                        msgs = await event.client.get_messages(entity, limit=limit)
                        lines = []
                        for m in reversed(msgs):
                            s = await m.get_sender()
                            name = (getattr(s, 'first_name', None) or
                                    getattr(s, 'title', None) or
                                    getattr(s, 'username', 'чел'))
                            lines.append(f"{name}: {m.text or '[медиа]'}")
                        tool_result = "\n".join(lines) or "нет сообщений"
                    except Exception as e:
                        tool_result = f"ошибка чтения: {e}"

                elif func_name == "search_telegram":
                    query = args.get("query", "")
                    scope = args.get("scope", "all")
                    try:
                        results = []
                        seen = set()

                        # 1. Поиск среди своих диалогов (local)
                        if scope in ["local", "all"]:
                            try:
                                dialogs = await event.client.get_dialogs(limit=100)
                                q_lower = query.lower()
                                for d in dialogs:
                                    title = d.name or ""
                                    username = getattr(d.entity, 'username', '') or ''
                                    if q_lower in title.lower() or q_lower in username.lower():
                                        link = f"https://t.me/{username}" if username else f"ID: {d.id}"
                                        results.append(f"[Личный чат] {title} ({link})")
                            except Exception as e:
                                logger.warning(f"Local search failed: {e}")

                        # 2. Глобальный поиск публичных каналов/групп/пользователей
                        if scope in ["global", "all"]:
                            # 2.1 Поиск через контакты/глобальный поиск Telegram API
                            from telethon.tl.functions.contacts import SearchRequest
                            try:
                                search_res = await event.client(SearchRequest(q=query, limit=15))
                                for chat_entity in getattr(search_res, 'chats', []):
                                    username = getattr(chat_entity, 'username', None)
                                    title = getattr(chat_entity, 'title', 'Без названия')
                                    members = getattr(chat_entity, 'participants_count', 0)
                                    if username and username.lower() not in seen:
                                        seen.add(username.lower())
                                        results.append(f"[Глобальный чат] {title} (~{members} участников)\nhttps://t.me/{username}")
                                for user_entity in getattr(search_res, 'users', []):
                                    username = getattr(user_entity, 'username', None)
                                    first_name = getattr(user_entity, 'first_name', '')
                                    last_name = getattr(user_entity, 'last_name', '')
                                    full_name = f"{first_name} {last_name}".strip() or "Без имени"
                                    if username and username.lower() not in seen:
                                        seen.add(username.lower())
                                        results.append(f"[Глобальный контакт] {full_name}\nhttps://t.me/{username}")
                            except Exception as e:
                                logger.warning(f"Telethon search failed: {e}")

                            # 2.2 Поиск через SearXNG по сайту t.me
                            from internet.searxng import search as searxng_search
                            try:
                                web_res = await searxng_search(f"site:t.me {query}", max_results=8)
                                import re
                                found_links = re.findall(r'https?://t\.me/([\w_]+)', web_res)
                                for un in found_links:
                                    un_lower = un.lower()
                                    if un_lower not in ["s", "share", "joinchat", "addstickers", "c", "bg", "contact"] and un_lower not in seen:
                                        seen.add(un_lower)
                                        results.append(f"[Глобальный чат (веб)] https://t.me/{un}")
                            except Exception as e:
                                logger.warning(f"Web search for telegram failed: {e}")

                        # 3. Поиск сообщений по ключевому слову во всех диалогах (messages)
                        if scope == "messages":
                            try:
                                from telethon.tl.functions.messages import SearchGlobalRequest
                                from telethon.tl.types import InputMessagesFilterEmpty
                                search_msgs = await event.client(SearchGlobalRequest(
                                    q=query,
                                    filter=InputMessagesFilterEmpty(),
                                    min_date=None,
                                    max_date=None,
                                    offset_id=0,
                                    offset_peer=None,
                                    limit=10
                                ))
                                for m in getattr(search_msgs, 'messages', []):
                                    text = m.text or "[Медиа]"
                                    try:
                                        chat = await event.client.get_entity(m.peer_id)
                                        chat_name = getattr(chat, 'title', getattr(chat, 'first_name', 'Чат'))
                                    except Exception:
                                        chat_name = f"Чат {m.peer_id}"
                                    results.append(f"[Сообщение из {chat_name}] {text[:150]}...")
                            except Exception as e:
                                logger.warning(f"Global message search failed: {e}")

                        tool_result = "\n\n".join(results[:15]) if results else "ничего не найдено"
                    except Exception as e:
                        tool_result = f"ошибка поиска: {e}"

                elif func_name == "add_schedule":
                    task_type = args.get("task_type")
                    target = args.get("target") or str(chat_id)
                    payload = args.get("payload", "")
                    schedule_type = args.get("schedule_type")
                    schedule_value = args.get("schedule_value")

                    try:
                        from config import local_now
                        import datetime
                        now = local_now()
                        next_run = None

                        if schedule_type == "once":
                            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
                                try:
                                    dt = datetime.datetime.strptime(schedule_value, fmt)
                                    from zoneinfo import ZoneInfo
                                    from config import TIMEZONE
                                    next_run_dt = dt.replace(tzinfo=ZoneInfo(TIMEZONE))
                                    next_run = next_run_dt.isoformat()
                                    break
                                except ValueError:
                                    continue
                            if not next_run:
                                raise ValueError("Неверный формат даты. Используй 'ГГГГ-ММ-ДД ЧЧ:ММ:СС'.")

                        elif schedule_type == "interval":
                            seconds = int(schedule_value)
                            next_run = (now + datetime.timedelta(seconds=seconds)).isoformat()

                        elif schedule_type == "daily":
                            hm = datetime.datetime.strptime(schedule_value, "%H:%M").time()
                            target_dt = now.replace(hour=hm.hour, minute=hm.minute, second=0, microsecond=0)
                            if target_dt <= now:
                                target_dt += datetime.timedelta(days=1)
                            next_run = target_dt.isoformat()

                        from memory.sqlite import add_db_schedule
                        sched_id = add_db_schedule(task_type, target, payload, schedule_type, schedule_value, next_run)
                        tool_result = f"✅ Задача успешно запланирована. ID в базе: {sched_id}. Следующий запуск: {next_run}"
                    except Exception as e:
                        tool_result = f"❌ Ошибка планирования: {e}"

                elif func_name == "list_schedules":
                    try:
                        from memory.sqlite import get_active_schedules
                        schedules = get_active_schedules()
                        if not schedules:
                            tool_result = "Нет активных запланированных задач."
                        else:
                            lines = []
                            for s in schedules:
                                sid, ttype, target, payload, stype, sval, lrun, nrun = s
                                lines.append(
                                    f"📌 ID: {sid} | Тип: {ttype} | Для: {target}\n"
                                    f"   Режим: {stype} ({sval}) | Последний запуск: {lrun or 'никогда'}\n"
                                    f"   Следующий запуск: {nrun or 'неизвестно'}\n"
                                    f"   Полезная нагрузка: {payload[:150]}..."
                                )
                            tool_result = "\n\n".join(lines)
                    except Exception as e:
                        tool_result = f"Ошибка получения списка задач: {e}"

                elif func_name == "delete_schedule":
                    try:
                        sid = int(args.get("schedule_id", 0))
                        from memory.sqlite import delete_db_schedule
                        success = delete_db_schedule(sid)
                        if success:
                            tool_result = f"✅ Задача с ID {sid} успешно удалена."
                        else:
                            tool_result = f"❌ Задача с ID {sid} не найдена в базе."
                    except Exception as e:
                        tool_result = f"Ошибка удаления задачи: {e}"

                # ── Telegram-действия (откладываем на events.py) ─────────────
                else:
                    pending_actions.append({"name": func_name, "args": args})
                    action_map = {
                        "send_message": f"сообщение {args.get('username')} будет отправлено",
                        "join_channel": f"подписка на {args.get('channel')} запланирована",
                        "leave_channel": f"выход из {args.get('channel')} запланирован",
                        "click_button": f"нажму кнопку [{args.get('index', '?')}]",
                        "set_timer": f"таймер на {args.get('seconds')}с установлен",
                        "react": f"поставлю реакцию {args.get('emoji')}",
                        "send_sticker": f"отправлю стикер '{args.get('query')}'",
                        "finish_task": f"задание завершено",
                    }
                    tool_result = action_map.get(func_name, "выполнено")

                # Добавляем результат в messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(tool_result)
                })

        # Если цикл закончился без ответа
        if final_text is None:
            logger.warning("[Agent] Цикл завершился без финального текста, fallback")
            prompt = get_chat_prompt(context, owner_name=owner_name)
            final_text = await generate_response(prompt)

        filtered = filter_response(final_text, last_msg=last_bot_msg)
        return filtered, pending_actions

    except Exception as e:
        error_str = str(e)
        if "All models failed" not in error_str:
            await alert_owner(event.client, f"Ошибка в think.py: {e}")
        else:
            logger.warning(f"[think] All models failed: {error_str}")
        return "не могу ответить прямо сейчас", []


async def run_scheduled_agent_task(client, target, task_text: str):
    """
    Запускает агентный цикл для выполнения произвольного задания в фоне.
    """
    from llm.prompts import get_task_prompt
    from llm.provider import generate_with_tools, generate_response
    from llm.tools import AGENT_TOOLS, execute_local_tool
    
    try:
        peer = int(target)
    except ValueError:
        peer = target

    system_prompt = get_task_prompt(task_text)
    messages = [{"role": "user", "content": system_prompt}]
    
    logger.info(f"📋 Starting scheduled agent task: {task_text}")
    
    final_text = None
    
    for step in range(MAX_AGENT_STEPS):
        try:
            text, tool_calls = await generate_with_tools(messages, AGENT_TOOLS)
            
            if tool_calls is None:
                final_text = text
                break
                
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in tool_calls
                ]
            })
            
            for tc in tool_calls:
                func_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                    
                logger.info(f"🔧 [Scheduled Agent] {func_name}({args})")
                
                tool_result = None
                
                # Выполняем инструменты напрямую
                local_result = execute_local_tool(func_name, args)
                if local_result is not None:
                    tool_result = local_result
                elif func_name == "search_web":
                    from internet.searxng import search as searxng_search
                    try:
                        tool_result = await searxng_search(args.get("query", ""))
                    except Exception as e:
                        tool_result = f"ошибка поиска: {e}"
                elif func_name == "execute_shell":
                    from host.executor import execute_shell, format_shell_result
                    cmd = args.get("command", "")
                    timeout = args.get("timeout", 30)
                    result = await execute_shell(cmd, timeout=timeout)
                    tool_result = format_shell_result(result)
                elif func_name == "read_file":
                    from host.executor import read_file
                    tool_result = await read_file(args.get("path", ""))
                elif func_name == "write_file":
                    from host.executor import write_file
                    tool_result = await write_file(args.get("path", ""), args.get("content", ""), args.get("append", False))
                elif func_name == "list_directory":
                    from host.executor import list_directory
                    tool_result = await list_directory(args.get("path", "."))
                elif func_name == "get_system_info":
                    from host.executor import get_system_info, format_system_info
                    info = await get_system_info()
                    tool_result = format_system_info(info)
                elif func_name == "download_file":
                    from host.executor import download_file
                    tool_result = await download_file(args.get("url", ""), args.get("dest", None))
                
                # Telegram-действия
                elif func_name == "send_message":
                    username = args.get("username", "")
                    msg_text = args.get("text", "")
                    try:
                        await client.send_message(username, msg_text)
                        tool_result = f"сообщение успешно отправлено в {username}"
                    except Exception as e:
                        tool_result = f"ошибка отправки сообщения: {e}"
                elif func_name == "join_channel":
                    from internet.telegram_reader import join_channel
                    tool_result = await join_channel(client, args.get("channel", ""))
                elif func_name == "leave_channel":
                    from internet.telegram_reader import leave_channel
                    tool_result = await leave_channel(client, args.get("channel", ""))
                elif func_name == "read_feed":
                    from internet.telegram_reader import get_recent_feed
                    tool_result = await get_recent_feed(client)
                elif func_name == "inspect_profile":
                    from internet.telegram_reader import inspect_profile
                    tool_result = await inspect_profile(client, args.get("target", ""))
                elif func_name == "read_chat_messages":
                    chat = args.get("chat", "")
                    limit = args.get("limit", 10)
                    try:
                        entity = await client.get_entity(chat.strip().replace("https://t.me/", ""))
                        msgs = await client.get_messages(entity, limit=limit)
                        lines = []
                        for m in reversed(msgs):
                            s = await m.get_sender()
                            name = (getattr(s, 'first_name', None) or getattr(s, 'username', 'чел'))
                            lines.append(f"{name}: {m.text or '[медиа]'}")
                        tool_result = "\n".join(lines) or "нет сообщений"
                    except Exception as e:
                        tool_result = f"ошибка чтения: {e}"
                elif func_name == "search_telegram":
                    query = args.get("query", "")
                    scope = args.get("scope", "all")
                    results = []
                    seen = set()
                    if scope in ["local", "all"]:
                        try:
                            dialogs = await client.get_dialogs(limit=50)
                            for d in dialogs:
                                title = d.name or ""
                                username = getattr(d.entity, 'username', '') or ''
                                if query.lower() in title.lower() or query.lower() in username.lower():
                                    results.append(f"[Личный чат] {title} (@{username})")
                        except Exception: pass
                    if scope in ["global", "all"]:
                        from telethon.tl.functions.contacts import SearchRequest
                        try:
                            search_res = await client(SearchRequest(q=query, limit=10))
                            for chat_entity in getattr(search_res, 'chats', []):
                                username = getattr(chat_entity, 'username', None)
                                if username:
                                    results.append(f"[Глобальный чат] {chat_entity.title} (@{username})")
                        except Exception: pass
                    tool_result = "\n\n".join(results[:10]) if results else "ничего не найдено"
                else:
                    tool_result = "выполнено (действие отложено/не поддерживается в фоновом режиме)"
                    
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(tool_result)
                })
        except Exception as e:
            logger.error(f"Error in scheduled task loop: {e}")
            break
            
    if final_text is None:
        final_text = "Задание выполнено."
        
    try:
        from brain.style_filter import filter_response
        filtered = filter_response(final_text)
        await client.send_message(peer, filtered)
    except Exception as e:
        logger.error(f"Failed to send final report to {target}: {e}")
