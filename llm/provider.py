"""
llm/provider.py — Мультипровайдер LLM с fallback цепочкой
"""
from openai import AsyncOpenAI
from config import (
    OPENROUTER_API_KEY, CODEXSALE_API_KEY, RUNIC_API_KEY,
    CUSTOM_API_KEY, CUSTOM_API_BASE_URL,
    LLM_MODELS, VISION_MODELS, STT_MODEL,
    GEMINI_API_KEY
)
import asyncio
import logging
import io

logger = logging.getLogger("provider")

openrouter_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY or "dummy",
    max_retries=0,
)

codexsale_client = AsyncOpenAI(
    base_url="https://codex.sale/v1",
    api_key=CODEXSALE_API_KEY or "dummy",
    max_retries=0,
)

runic_client = AsyncOpenAI(
    base_url="https://runic.morikotikk.dev/v1",
    api_key=RUNIC_API_KEY or "dummy",
    max_retries=0,
)

# Google Gemini — OpenAI-совместимый эндпоинт
gemini_client = AsyncOpenAI(
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    api_key=GEMINI_API_KEY or "dummy",
    max_retries=0,
)

# Кастомный OpenAI-совместимый провайдер (LMStudio, Ollama, Groq, Together и т.д.)
custom_client = AsyncOpenAI(
    base_url=CUSTOM_API_BASE_URL or "http://localhost:11434/v1",
    api_key=CUSTOM_API_KEY or "dummy",
    max_retries=0,
) if CUSTOM_API_BASE_URL else None

FATAL_ERROR_CODES = {401, 403}


def _get_client_and_model(model: str):
    """Возвращает (client, real_model_id) по префиксу модели."""
    if model.startswith("gemini/"):
        if not GEMINI_API_KEY:
            raise ValueError("gemini API key is not configured")
        return gemini_client, model[len("gemini/"):]
    elif model.startswith("custom/"):
        real_model = model[len("custom/"):]
        if custom_client is None or not CUSTOM_API_KEY:
            logger.warning("custom_client не настроен (CUSTOM_API_BASE_URL или CUSTOM_API_KEY пуст), пропускаем")
            raise ValueError("custom_client not configured")
        return custom_client, real_model
    elif model.startswith("codexsale/"):
        if not CODEXSALE_API_KEY:
            raise ValueError("codexsale API key is not configured")
        return codexsale_client, model[len("codexsale/"):]
    elif model.startswith("runic/"):
        if not RUNIC_API_KEY:
            raise ValueError("runic API key is not configured")
        return runic_client, model[len("runic/"):]
    else:
        if not OPENROUTER_API_KEY:
            raise ValueError("openrouter API key is not configured")
        return openrouter_client, model


def _supports_tools(model: str) -> bool:
    """Модели с поддержкой function calling."""
    return (
        model.startswith("codexsale/")
        or model.startswith("runic/")
        or model.startswith("custom/")   # кастомные провайдеры как правило поддерживают
    )


async def generate_response(prompt: str, is_vision: bool = False,
                            image_url: str = None, temperature: float = 0.85) -> str:
    """Простая генерация текста. Пробует все модели по очереди."""
    from memory.sqlite import get_setting
    primary = get_setting("primary_model")
    models = list(VISION_MODELS) if is_vision else list(LLM_MODELS)
    if primary:
        models = [primary] + [m for m in models if m != primary]

    if is_vision and image_url:
        logger.info(f"Vision request: prompt_len={len(prompt)}, image_url_len={len(image_url)}, models={models}, prefix={image_url[:60]}... suffix={image_url[-20:] if len(image_url) > 20 else ''}")
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        }]
    else:
        messages = [{"role": "user", "content": prompt}]

    last_error = None
    for model in models:
        try:
            logger.info(f"🤖 Trying model: {model}...")
            client, real_model = _get_client_and_model(model)
            response = await client.chat.completions.create(
                model=real_model,
                messages=messages,
                temperature=temperature,
            )
            logger.info(f"Response from {model} received. Type of response: {type(response)}")
            if not response.choices:
                logger.warning(f"⚠️ Модель {model} вернула пустой список choices. Response: {response}")
                continue
            content = response.choices[0].message.content
            if content:
                logger.info(f"✅ Модель {model} успешно ответила: {content[:150]}...")
                return content
            else:
                logger.warning(f"⚠️ Модель {model} вернула пустой content. Response: {response}")
                continue
        except Exception as e:
            logger.warning(f"❌ Model {model} failed: {str(e)}")
            import traceback
            logger.warning(f"Traceback for {model}: {traceback.format_exc()}")
            last_error = e
            if hasattr(e, 'status_code') and e.status_code in FATAL_ERROR_CODES:
                logger.error(f"❌ Фатальная ошибка {e.status_code} для {model}")
            await asyncio.sleep(0.3)

    logger.error(f"All models failed. Last: {last_error}")
    if is_vision:
        return "не удалось распознать изображение"
    return "не могу ответить прямо сейчас, попробуй ещё раз"


async def generate_with_tools(messages: list, tools: list, temperature: float = 0.85):
    """
    Агентный вызов с function calling.
    Возвращает (text_content, tool_calls_list | None)
    """
    from memory.sqlite import get_setting
    primary = get_setting("primary_model")
    models = list(LLM_MODELS)
    if primary:
        models = [primary] + [m for m in models if m != primary]

    last_error = None
    for model in models:
        try:
            client, real_model = _get_client_and_model(model)

            if _supports_tools(model):
                response = await client.chat.completions.create(
                    model=real_model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=temperature,
                )
                msg = response.choices[0].message
                if msg.tool_calls:
                    return None, msg.tool_calls
                content = msg.content
                if content:
                    return content, None
                continue
            else:
                response = await client.chat.completions.create(
                    model=real_model,
                    messages=messages,
                    temperature=temperature,
                )
                content = response.choices[0].message.content
                if content:
                    return content, None
                continue

        except Exception as e:
            logger.warning(f"[tools] Model {model} failed: {str(e)[:120]}")
            last_error = e
            await asyncio.sleep(0.3)

    logger.error(f"[tools] All models failed. Last: {last_error}")
    raise RuntimeError(f"All models failed. Last error: {last_error}")

async def stream_with_tools(messages: list, tools: list, temperature: float = 0.85):
    """
    Агентный вызов с function calling и стримингом текста.
    Генерирует ('content', text_chunk) или ('tool_calls', [tool_call_objects])
    """
    from memory.sqlite import get_setting
    import json
    primary = get_setting("primary_model")
    models = list(LLM_MODELS)
    if primary:
        models = [primary] + [m for m in models if m != primary]

    last_error = None
    for model in models:
        try:
            client, real_model = _get_client_and_model(model)
            if _supports_tools(model):
                response = await client.chat.completions.create(
                    model=real_model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=temperature,
                    stream=True
                )
                
                is_tool_call = False
                tool_calls_dict = {}
                
                async for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    
                    if delta.tool_calls:
                        is_tool_call = True
                        for tc_chunk in delta.tool_calls:
                            idx = tc_chunk.index
                            if idx not in tool_calls_dict:
                                tool_calls_dict[idx] = {
                                    "id": tc_chunk.id or "",
                                    "type": "function",
                                    "function": {"name": tc_chunk.function.name or "", "arguments": ""}
                                }
                            if tc_chunk.function.arguments:
                                tool_calls_dict[idx]["function"]["arguments"] += tc_chunk.function.arguments
                    elif delta.content and not is_tool_call:
                        yield ('content', delta.content)
                        
                if is_tool_call:
                    class MockFunction:
                        def __init__(self, name, arguments):
                            self.name = name
                            self.arguments = arguments
                    class MockToolCall:
                        def __init__(self, id, type, function):
                            self.id = id
                            self.type = type
                            self.function = function
                    
                    final_calls = []
                    for idx, tc in tool_calls_dict.items():
                        final_calls.append(MockToolCall(
                            id=tc["id"],
                            type=tc["type"],
                            function=MockFunction(tc["function"]["name"], tc["function"]["arguments"])
                        ))
                    yield ('tool_calls', final_calls)
                return
            else:
                response = await client.chat.completions.create(
                    model=real_model,
                    messages=messages,
                    temperature=temperature,
                    stream=True
                )
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield ('content', chunk.choices[0].delta.content)
                return

        except Exception as e:
            logger.warning(f"[stream] Model {model} failed: {str(e)[:120]}")
            last_error = e
            await asyncio.sleep(0.3)

    logger.error(f"[stream] All models failed. Last: {last_error}")
    raise RuntimeError(f"All models failed. Last error: {last_error}")

def _extract_transcription_text(response) -> str | None:
    """Извлекает текст из разных форматов ответа Whisper API."""
    if response is None:
        return None
    if isinstance(response, str):
        text = response.strip()
        return text if text else None
    text = getattr(response, "text", None)
    if text:
        return str(text).strip()
    if isinstance(response, dict):
        text = response.get("text")
        if text:
            return str(text).strip()
    return None


async def _try_transcribe(client, audio_bytes: bytes, audio_format: str, model: str, response_format: str):
    """Одна попытка транскрибации."""
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = f"audio.{audio_format}"
    response = await client.audio.transcriptions.create(
        model=model,
        file=audio_file,
        language="ru",
        response_format=response_format,
    )
    return _extract_transcription_text(response)


async def transcribe_audio(audio_bytes: bytes, audio_format: str = "ogg") -> str | None:
    """Транскрибация аудио через OpenAI-совместимый API.

    Запускает несколько провайдеров параллельно и возвращает первый
    непустой результат. Telegram voice = OGG Opus, отправляем как есть.
    """
    real_model = STT_MODEL.replace("openai/", "")

    tasks = []
    names = []

    # Основной STT-провайдер
    if CODEXSALE_API_KEY:
        tasks.append(_try_transcribe(codexsale_client, audio_bytes, audio_format, real_model, "json"))
        names.append("codexsale")

    # Фолбэк на OpenRouter Whisper
    if OPENROUTER_API_KEY:
        tasks.append(_try_transcribe(openrouter_client, audio_bytes, audio_format, "openai/whisper-large-v3", "json"))
        names.append("openrouter")

    if not tasks:
        logger.error("[STT] Нет настроенных STT-провайдеров")
        return None

    logger.info(f"[STT] Parallel transcription start ({', '.join(names)}), format={audio_format}, size={len(audio_bytes)} bytes")
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for name, result in zip(names, results):
        if isinstance(result, Exception):
            logger.warning(f"[STT] {name} failed: {result}")
            continue
        if result:
            logger.info(f"[STT] ✅ {name} result: {result[:100]}...")
            return result

    logger.error("[STT] All STT providers returned empty/failed")
    return None
