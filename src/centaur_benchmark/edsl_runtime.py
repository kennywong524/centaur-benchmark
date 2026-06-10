"""EDSL execution mode: remote Expected Parrot Jobs vs local API proxy."""

from __future__ import annotations

import os
from typing import Any


def use_remote_inference() -> bool:
    """Default False: local API proxy. Set CENTAUR_EDSL_REMOTE=1 for remote Jobs."""
    return os.environ.get("CENTAUR_EDSL_REMOTE", "0").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def edsl_run_kwargs(
    *,
    description: str,
    visibility: str = "private",
    progress_bar: bool = False,
    verbose: bool = False,
    n: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build kwargs for Survey/Jobs.run() using remote Jobs or local API proxy."""
    kwargs: dict[str, Any] = {
        "progress_bar": progress_bar,
        "verbose": verbose,
        "print_exceptions": True,
        "stop_on_exception": False,
        "check_api_keys": False,
        **extra,
    }
    if n is not None:
        kwargs["n"] = n
    if use_remote_inference():
        kwargs.update(
            {
                "use_api_proxy": False,
                "disable_remote_inference": False,
                "remote_inference_description": description[:200],
                "remote_inference_results_visibility": visibility,
            }
        )
    else:
        kwargs.update(
            {
                "use_api_proxy": True,
                "disable_remote_inference": True,
            }
        )
    return kwargs
