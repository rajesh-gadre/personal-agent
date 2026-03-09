from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from shared.config.settings import settings
from shared.llm.base import LLMProvider


def get_llm(
    provider: LLMProvider | None = None,
    model: str | None = None,
    **kwargs,
) -> BaseChatModel:
    """Return a LangChain chat model based on provider config."""
    provider = provider or settings.default_llm_provider
    model = model or settings.default_llm_model

    if provider == "anthropic":
        return ChatAnthropic(
            model=model,
            api_key=settings.anthropic_api_key,
            **kwargs,
        )
    elif provider == "openai":
        return ChatOpenAI(
            model=model,
            api_key=settings.openai_api_key,
            **kwargs,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
