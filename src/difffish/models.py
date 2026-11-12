"""Chat models on the configured endpoint, one per deployment name."""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from difffish.config import api_key, get_settings


def get_model(name: str) -> ChatOpenAI:
    s = get_settings()
    return ChatOpenAI(
        base_url=s.base_url,
        api_key=api_key(),
        model=name,
        max_retries=s.max_retries,
        timeout=s.timeout,
    )


def get_structured_model(name: str, schema: type[BaseModel]):
    """A model that returns an instance of ``schema``.

    Defaults to function calling: on this endpoint the ``json_schema`` method
    has corrupted date fields.
    """
    return get_model(name).with_structured_output(schema, method=get_settings().structured_output_method)
