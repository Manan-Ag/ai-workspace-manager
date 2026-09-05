from fastapi import HTTPException, status

from app.services.llm import (
    LLMProvider,
    ProviderConfigurationError,
    get_llm_provider,
)


def require_llm_provider() -> LLMProvider:
    try:
        return get_llm_provider()
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Gemini is not configured. Add GEMINI_API_KEY to the backend environment.",
        ) from exc
