"""Native Together helpers for DeepSeek dedicated endpoints.

This module is intentionally small and separate from the EDSL runtime. Together
serves DeepSeek-V3.1 as a dedicated endpoint rather than through the normal
serverless chat path, so we call the OpenAI-compatible chat endpoint directly
when CENTAUR_DEEPSEEK_ROUTE=together.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib import error, request


DEEPSEEK_MODEL_ID = "deepseek-ai/DeepSeek-V3.1"


def use_together_deepseek(model_id: str | None) -> bool:
    """Return True when DeepSeek should be routed through Together."""
    route = os.environ.get("CENTAUR_DEEPSEEK_ROUTE", "").strip().lower()
    return str(model_id or "") == DEEPSEEK_MODEL_ID and route == "together"


def together_endpoint_model() -> str:
    """Model/endpoint identifier to pass to Together chat completions."""
    endpoint_name = os.environ.get("CENTAUR_TOGETHER_DEEPSEEK_ENDPOINT_NAME", "").strip()
    if endpoint_name:
        return endpoint_name
    endpoint = os.environ.get("CENTAUR_TOGETHER_DEEPSEEK_ENDPOINT", "").strip()
    if endpoint:
        if endpoint.startswith("endpoint-"):
            try:
                from together import Together

                ep = Together(api_key=os.environ.get("TOGETHER_API_KEY")).endpoints.retrieve(endpoint)
                name = str(getattr(ep, "name", "") or "").strip()
                if name:
                    return name
            except Exception:
                pass
        return endpoint
    return os.environ.get("CENTAUR_TOGETHER_DEEPSEEK_MODEL", DEEPSEEK_MODEL_ID).strip()


def together_chat_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int | None = None,
    temperature: float = 0.5,
    timeout_sec: int | None = None,
    retries: int | None = None,
) -> str:
    """Call Together's OpenAI-compatible chat endpoint and return text."""
    api_key = os.environ.get("TOGETHER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TOGETHER_API_KEY is required for Together DeepSeek calls")

    model = together_endpoint_model()
    if os.environ.get("CENTAUR_TOGETHER_USE_SDK", "1").strip().lower() not in {"0", "false", "no"}:
        try:
            from together import Together

            client = Together(api_key=api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=int(timeout_sec or os.environ.get("CENTAUR_TOGETHER_TIMEOUT_SEC", "900")),
            )
            choice = response.choices[0]
            content = getattr(getattr(choice, "message", None), "content", None)
            if content is None:
                content = getattr(choice, "text", "")
            return str(content or "").strip()
        except Exception as exc:
            if os.environ.get("CENTAUR_TOGETHER_SDK_ONLY", "").strip().lower() in {
                "1",
                "true",
                "yes",
            }:
                raise
            last_sdk_error = exc
    else:
        last_sdk_error = None

    url = os.environ.get(
        "CENTAUR_TOGETHER_CHAT_URL",
        "https://api.together.ai/v1/chat/completions",
    ).strip()
    timeout = int(timeout_sec or os.environ.get("CENTAUR_TOGETHER_TIMEOUT_SEC", "900"))
    attempts = int(retries or os.environ.get("CENTAUR_TOGETHER_MAX_ATTEMPTS", "4"))

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = last_sdk_error
    for attempt in range(1, attempts + 1):
        req = request.Request(url, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError(f"Together response had no choices: {data!r}")
            msg = choices[0].get("message") or {}
            text = msg.get("content")
            if text is None:
                text = choices[0].get("text", "")
            return str(text or "").strip()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(
                f"Together HTTP {exc.code} on attempt {attempt}: {detail[:1000]}"
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc

        if attempt < attempts:
            time.sleep(min(30, 2**attempt))

    raise RuntimeError(f"Together chat failed after {attempts} attempts: {last_error}")
