"""The one place that builds the language model, so both agents get the same settings."""

from langchain_openrouter import ChatOpenRouter

from app.config import Settings


def build_model(settings: Settings, model: str) -> ChatOpenRouter:
    """The chat model `model` (an OpenRouter id) with the reasoning, timeout, retries and routing from the settings.

    Every parameter sent must be one all the models we use accept, because providers that do
    not support one are skipped (`require_parameters`).
    """
    return ChatOpenRouter(
        model=model,
        openrouter_api_key=settings.openrouter_api_key,
        reasoning={"effort": settings.reasoning_effort},
        timeout=settings.model_timeout_seconds * 1000,  # in milliseconds: a stuck call is cut off and retried
        max_retries=settings.model_max_retries,
        # Prefer fast providers, and only those that support every parameter we send (e.g. a JSON
        # schema): some providers silently ignore it and answer with an empty object.
        openrouter_provider={"sort": "latency", "require_parameters": True},
    )
