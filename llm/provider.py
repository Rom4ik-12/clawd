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
            client, real_model = _get_client_and_model(model)
            response = await client.chat.completions.create(
                model=real_model,
                messages=messages,
                temperature=temperature,
            )
            content = response.choices[0].message.content
            if content:
                logger.debug(f"✅ Модель {model} ответила")
                return content
            else:
                logger.warning(f"⚠️ Модель {model} вернула пустой ответ")
                continue
        except Exception as e:
            logger.warning(f"Model {model} failed: {str(e)[:120]}")
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


async def transcribe_audio(audio_bytes: bytes, audio_format: str = "wav") -> str | None:
    """Транскрибация аудио через OpenAI-совместимый API."""
    real_model = STT_MODEL.replace("openai/", "")

    # Пробуем codexsale
    try:
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"audio.{audio_format}"
        response = await codexsale_client.audio.transcriptions.create(
            model=real_model,
            file=audio_file,
            language="ru",
            response_format="text",
        )
        result = response.strip() if isinstance(response, str) else str(response).strip()
        if result:
            return result
    except Exception as e:
        logger.warning(f"[STT] codexsale failed: {e}, trying openrouter whisper...")

    # Фолбэк: openrouter whisper
    try:
        audio_file2 = io.BytesIO(audio_bytes)
        audio_file2.name = f"audio.{audio_format}"
        response2 = await openrouter_client.audio.transcriptions.create(
            model="openai/whisper-large-v3",
            file=audio_file2,
            language="ru",
            response_format="text",
        )
        result2 = response2.strip() if isinstance(response2, str) else str(response2).strip()
        if result2:
            return result2
    except Exception as e2:
        logger.error(f"[STT] All STT failed: {e2}")

    return None
