"""EDSL execution mode: remote Jobs, EP proxy, or direct provider keys."""

from __future__ import annotations

import os
import re
from types import MethodType
from typing import Any

def ensure_edsl_timeouts() -> None:
    """Keep EDSL timeouts explicit while allowing run scripts to tune them.

    Earlier versions always forced 1800s here. That was helpful for long
    frontier-model completions, but it also made proxy-only failures hang for
    half an hour before the resumable runner could repair or skip them. Respect
    the caller's env override so batch runs can choose the right trade-off.
    """
    timeout_sec = os.environ.get("CENTAUR_EDSL_TIMEOUT_SEC", "").strip()
    if not timeout_sec:
        timeout_sec = os.environ.get("EDSL_API_TIMEOUT", "").strip()
    if not timeout_sec:
        timeout_sec = "1800"
    os.environ["EDSL_API_TIMEOUT"] = timeout_sec
    os.environ["REMOTE_PROXY_TIMEOUT"] = os.environ.get(
        "REMOTE_PROXY_TIMEOUT", timeout_sec
    )
    try:
        from edsl.config import CONFIG

        CONFIG.EDSL_API_TIMEOUT = timeout_sec
    except ImportError:
        pass


_EP_PROXY_ONLY_MODEL_PREFIXES = (
    "openai/gpt-oss",
    "deepseek-ai/",
)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() not in {"", "0", "false", "no", "off"}


def execution_mode() -> str:
    """Return one of: ep_proxy, direct, mixed, remote.

    Legacy compatibility:
    - CENTAUR_EDSL_REMOTE=1 still means remote Expected Parrot Jobs.
    - With no explicit mode, preserve the old local Expected Parrot proxy behavior.
    """
    explicit = os.environ.get("CENTAUR_EDSL_MODE", "").strip().lower()
    aliases = {
        "proxy": "ep_proxy",
        "local_proxy": "ep_proxy",
        "expected_parrot": "ep_proxy",
        "ep": "ep_proxy",
        "provider": "direct",
        "local_provider": "direct",
    }
    if explicit:
        mode = aliases.get(explicit, explicit)
        if mode not in {"ep_proxy", "direct", "mixed", "remote"}:
            raise ValueError(
                "CENTAUR_EDSL_MODE must be one of ep_proxy, direct, mixed, remote "
                f"(got {explicit!r})"
            )
        return mode
    if _truthy(os.environ.get("CENTAUR_EDSL_REMOTE")):
        return "remote"
    return "ep_proxy"


def use_remote_inference() -> bool:
    """Compatibility helper: True only for remote Expected Parrot Jobs."""
    return execution_mode() == "remote"


def _safe_env_suffix(model_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", model_id).strip("_").upper()


def model_uses_ep_proxy(model_id: str | None) -> bool:
    """Whether this model should use the Expected Parrot API proxy for this call."""
    if model_uses_remote_jobs(model_id):
        return False
    mode = execution_mode()
    if mode == "remote":
        return False
    if mode == "ep_proxy":
        return True
    if mode == "direct":
        return False
    # mixed: direct provider keys where possible, EP proxy for proxy-only/open-weight rows.
    mid = str(model_id or "")
    forced = [
        x.strip()
        for x in os.environ.get("CENTAUR_EP_PROXY_MODELS", "").split(",")
        if x.strip()
    ]
    if any(mid == pattern or mid.startswith(pattern.rstrip("*")) for pattern in forced):
        return True
    if any(mid.startswith(prefix) for prefix in _EP_PROXY_ONLY_MODEL_PREFIXES):
        return True
    if mid.startswith(("anthropic/", "google/")) and not _truthy(
        os.environ.get("CENTAUR_DIRECT_ENABLE_VENDOR_ALIASES")
    ):
        # These benchmark IDs have historically been EP aliases. Use direct mode
        # for them only after alias env vars have been verified.
        return True
    return False


def model_uses_remote_jobs(model_id: str | None) -> bool:
    """Whether this model should use Expected Parrot remote Jobs in mixed mode.

    This is intentionally opt-in. It lets public replication runs route a flaky
    proxy-only model, such as DeepSeek through EP, to remote Jobs while keeping
    OpenAI/Anthropic/Google calls on direct provider keys.
    """
    mode = execution_mode()
    if mode == "remote":
        return True
    mid = str(model_id or "")
    forced = [
        x.strip()
        for x in os.environ.get("CENTAUR_REMOTE_JOB_MODELS", "").split(",")
        if x.strip()
    ]
    return any(mid == pattern or mid.startswith(pattern.rstrip("*")) for pattern in forced)


def provider_model_name(model_id: str) -> tuple[str, dict[str, Any]]:
    """Map benchmark model IDs to EDSL direct-provider Model(...) arguments.

    Environment aliases let us keep task YAMLs stable while trying provider-native
    names for public replication runs, for example:
      CENTAUR_MODEL_ALIAS_ANTHROPIC_CLAUDE_OPUS_4_8=claude-opus-4-20250514
      CENTAUR_MODEL_ALIAS_GOOGLE_GEMINI_3_1_PRO=gemini-2.5-pro
    """
    if model_uses_remote_jobs(model_id):
        return str(model_id), {}

    if model_uses_ep_proxy(model_id):
        return str(model_id), {}

    original = str(model_id)
    mid = original
    alias = os.environ.get(f"CENTAUR_MODEL_ALIAS_{_safe_env_suffix(mid)}")
    if alias:
        mid = alias.strip()

    kwargs: dict[str, Any] = {}
    if original.startswith("anthropic/"):
        kwargs["service_name"] = "anthropic"
        if mid.startswith("anthropic/"):
            mid = mid.split("/", 1)[1]
    elif original.startswith("google/"):
        kwargs["service_name"] = "google"
        if mid.startswith("google/"):
            mid = mid.split("/", 1)[1]
    elif mid.startswith("anthropic/"):
        kwargs["service_name"] = "anthropic"
        mid = mid.split("/", 1)[1]
    elif mid.startswith("google/"):
        kwargs["service_name"] = "google"
        mid = mid.split("/", 1)[1]
    elif mid.startswith("deepseek-ai/"):
        # Direct DeepSeek API does not use deepseek-ai/... model IDs. Keep these
        # on the EP proxy unless the user explicitly aliases them.
        kwargs["service_name"] = os.environ.get("CENTAUR_DEEPSEEK_SERVICE", "deep_infra")
    elif mid.startswith("openai/"):
        # GPT-OSS is proxy/open-weight by default; if explicitly forced direct,
        # preserve the service override so the failure is easy to understand.
        kwargs["service_name"] = os.environ.get("CENTAUR_OPEN_WEIGHT_SERVICE", "deep_infra")
    elif mid.startswith(("gpt-5", "o3-", "o4-")):
        kwargs["service_name"] = "openai_v2"
    elif mid.startswith(("gpt-", "chatgpt-")):
        kwargs["service_name"] = "openai"
    return mid, kwargs


def make_model(model_id: str, **kwargs: Any):
    """Create an EDSL Model with Centaur routing fixes applied."""
    from edsl import Model

    provider_id, provider_kwargs = provider_model_name(model_id)
    model = Model(provider_id, **{**provider_kwargs, **kwargs})
    if provider_kwargs.get("service_name") == "anthropic" and provider_id in {
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-fable-5",
    }:
        _patch_anthropic_no_temperature(model)
    return model


def _patch_anthropic_no_temperature(model: Any) -> None:
    """Patch EDSL's Anthropic wrapper for models that reject temperature."""

    async def async_execute_model_call_no_temperature(
        self,
        user_prompt: str,
        system_prompt: str = "",
        files_list: Any = None,
        cache_key: str | None = None,
    ) -> dict[str, Any]:
        from anthropic import AsyncAnthropic

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]
        client = AsyncAnthropic(api_key=self.api_token)
        response = await client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=messages,
        )
        return response.model_dump()

    model.async_execute_model_call = MethodType(
        async_execute_model_call_no_temperature, model
    )


def edsl_run_kwargs(
    *,
    description: str,
    model_id: str | None = None,
    visibility: str = "private",
    progress_bar: bool = False,
    verbose: bool = False,
    n: int | None = None,
    cache: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    """Build kwargs for Survey/Jobs.run() using remote Jobs or local API proxy.

  Generation should use cache=False (default) so replicates are independent fresh
  API calls. Judging may pass cache=True to reuse identical pairwise evaluations.
    """
    ensure_edsl_timeouts()
    kwargs: dict[str, Any] = {
        "progress_bar": progress_bar,
        "verbose": verbose,
        "print_exceptions": True,
        "stop_on_exception": False,
        "check_api_keys": False,
        "cache": cache,
        "disable_remote_cache": not cache,
        "fresh": not cache,
        "remote_cache_description": description[:200],
        **extra,
    }
    if n is not None:
        kwargs["n"] = n
    mode = execution_mode()
    if mode == "remote" or model_uses_remote_jobs(model_id):
        kwargs.update(
            {
                "use_api_proxy": False,
                "disable_remote_inference": False,
                "remote_inference_description": description[:200],
                "remote_inference_results_visibility": visibility,
            }
        )
    elif model_uses_ep_proxy(model_id):
        kwargs.update(
            {
                "use_api_proxy": True,
                "disable_remote_inference": True,
            }
        )
    else:
        kwargs.update(
            {
                "use_api_proxy": False,
                "disable_remote_inference": True,
            }
        )
    return kwargs
