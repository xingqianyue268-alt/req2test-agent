"""OpenAI-compatible model adapter with defensive JSON parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from .config import LLMSettings


def build_chat_model(settings: LLMSettings):
    if settings.mode != "openai_compatible":
        raise ValueError("演示模式不需要创建大模型客户端")

    from langchain_openai import ChatOpenAI

    api_key = settings.api_key or "ollama"
    return ChatOpenAI(
        model=settings.model,
        api_key=api_key,
        base_url=settings.base_url,
        temperature=settings.temperature,
        timeout=settings.timeout_seconds,
        max_retries=1,
    )


def _normalise_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def extract_json(text: str) -> Any:
    """Extract a JSON object/array from model output, including fenced blocks."""

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    candidates: list[str] = []
    first_object, last_object = text.find("{"), text.rfind("}")
    first_array, last_array = text.find("["), text.rfind("]")
    if first_object >= 0 and last_object > first_object:
        candidates.append(text[first_object : last_object + 1])
    if first_array >= 0 and last_array > first_array:
        candidates.append(text[first_array : last_array + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("模型返回内容中未找到有效 JSON")


def invoke_json(model, system_prompt: str, user_prompt: str) -> Any:
    from langchain_core.messages import HumanMessage, SystemMessage

    response = model.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    )
    return extract_json(_normalise_content(response.content))
