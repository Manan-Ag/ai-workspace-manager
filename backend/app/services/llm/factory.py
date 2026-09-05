from functools import lru_cache

from app.core.config import get_settings
from app.services.llm.gemini import GeminiProvider
from app.services.llm.provider import LLMProvider, ProviderConfigurationError


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ProviderConfigurationError(
            "Gemini is not configured. Add GEMINI_API_KEY to the root .env file."
        )
    return GeminiProvider(
        api_key=settings.gemini_api_key,
        default_model=settings.gemini_chat_model,
        request_timeout_seconds=settings.gemini_request_timeout_seconds,
    )
