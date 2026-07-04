#!/usr/bin/env python3
"""Manage a Together dedicated endpoint for base DeepSeek-V3.1 inference.

This is not a fine-tuning script. It creates or controls a dedicated endpoint
serving the base model `deepseek-ai/DeepSeek-V3.1` for normal chat completions.
Use it for the flaky DeepSeek generation/judging rows, then stop the endpoint.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any


MODEL_ID = "deepseek-ai/DeepSeek-V3.1"
DEFAULT_DISPLAY_NAME = "centaur-deepseek-v31"


def _client():
    try:
        from together import Together
    except ImportError as exc:
        raise SystemExit(
            "The together package is not installed in this venv. "
            "Run: .venv/bin/pip install together"
        ) from exc
    return Together(api_key=os.environ.get("TOGETHER_API_KEY"))


def _dump_endpoint(ep: Any) -> None:
    fields = [
        "id",
        "name",
        "display_name",
        "model",
        "hardware",
        "state",
        "status",
        "type",
        "inactive_timeout",
    ]
    for field in fields:
        value = getattr(ep, field, None)
        if value is not None:
            print(f"{field}: {value}")
    autoscaling = getattr(ep, "autoscaling", None)
    if autoscaling is not None:
        print(f"autoscaling: {autoscaling}")


def list_hardware() -> None:
    client = _client()
    resp = client.endpoints.list_hardware(model=MODEL_ID)
    rows = getattr(resp, "object", None) or getattr(resp, "data", None) or resp
    print(rows)


def list_endpoints() -> None:
    client = _client()
    resp = client.endpoints.list(mine=True, type="dedicated")
    endpoints = getattr(resp, "data", None) or []
    if not endpoints:
        print("No dedicated endpoints found.")
        return
    for ep in endpoints:
        print("-" * 72)
        _dump_endpoint(ep)


def create_endpoint(args: argparse.Namespace) -> None:
    client = _client()
    print(
        "Creating Together dedicated endpoint for base model "
        f"{MODEL_ID} on {args.hardware}..."
    )
    ep = client.endpoints.create(
        model=MODEL_ID,
        hardware=args.hardware,
        autoscaling={"min_replicas": args.min_replicas, "max_replicas": args.max_replicas},
        display_name=args.display_name,
        inactive_timeout=args.inactive_timeout,
        state="STARTED" if args.start else "STOPPED",
    )
    _dump_endpoint(ep)
    endpoint_id = getattr(ep, "id", None)
    if endpoint_id:
        print("\nAdd this to .env while using the endpoint:")
        print(f'CENTAUR_TOGETHER_DEEPSEEK_ENDPOINT="{endpoint_id}"')
        print('CENTAUR_DEEPSEEK_ROUTE="together"')
    if args.wait and endpoint_id:
        wait_endpoint(endpoint_id, timeout=args.wait_timeout)


def wait_endpoint(endpoint_id: str, *, timeout: int) -> None:
    client = _client()
    deadline = time.time() + timeout
    while True:
        ep = client.endpoints.retrieve(endpoint_id)
        state = str(getattr(ep, "state", "") or getattr(ep, "status", "")).upper()
        autoscaling = getattr(ep, "autoscaling", None)
        ready = int(getattr(autoscaling, "ready_replicas", 0) or 0)
        current = int(getattr(autoscaling, "current_replicas", 0) or 0)
        print(
            f"endpoint={endpoint_id} state={state or 'unknown'} "
            f"ready_replicas={ready} current_replicas={current}"
        )
        if state in {"STARTED", "READY", "RUNNING"} and ready > 0:
            _dump_endpoint(ep)
            return
        if time.time() > deadline:
            raise SystemExit(f"Timed out waiting for endpoint {endpoint_id}")
        time.sleep(20)


def update_state(endpoint_id: str, state: str) -> None:
    client = _client()
    ep = client.endpoints.update(endpoint_id, state=state)
    _dump_endpoint(ep)


def delete_endpoint(endpoint_id: str) -> None:
    client = _client()
    client.endpoints.delete(endpoint_id)
    print(f"Deleted endpoint {endpoint_id}")


def _print_endpoint_debug() -> None:
    from centaur_benchmark.together_runtime import (
        together_endpoint_id,
        together_endpoint_info,
        together_endpoint_model,
    )

    endpoint_id = together_endpoint_id()
    print(f"CENTAUR_TOGETHER_DEEPSEEK_ENDPOINT={endpoint_id or '(unset)'}")
    print(
        "CENTAUR_TOGETHER_DEEPSEEK_ENDPOINT_NAME="
        f"{os.environ.get('CENTAUR_TOGETHER_DEEPSEEK_ENDPOINT_NAME', '').strip() or '(unset)'}"
    )
    if endpoint_id:
        info = together_endpoint_info()
        if info:
            print("Endpoint retrieve():")
            for key in (
                "id",
                "name",
                "display_name",
                "model",
                "hardware",
                "state",
                "ready_replicas",
                "current_replicas",
            ):
                print(f"  {key}: {info.get(key)}")
    print(f"Together chat model identifier: {together_endpoint_model()}")


def smoke(prompt: str, max_tokens: int, *, wait_first: bool, wait_timeout: int) -> None:
    from centaur_benchmark.together_runtime import together_chat_completion, together_endpoint_id

    endpoint_id = together_endpoint_id()
    if wait_first and endpoint_id:
        print(f"Waiting for endpoint {endpoint_id} to become ready...")
        wait_endpoint(endpoint_id, timeout=wait_timeout)
    _print_endpoint_debug()
    text = together_chat_completion(
        system_prompt="Return only the requested answer.",
        user_prompt=prompt,
        max_tokens=max_tokens,
        temperature=0.2,
        timeout_sec=300,
        retries=2,
    )
    print(f"chars={len(text)}")
    print(text[:2000])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("hardware")
    sub.add_parser("list")

    create = sub.add_parser("create")
    create.add_argument("--hardware", default="4x_nvidia_b200_180gb_sxm")
    create.add_argument("--display-name", default=DEFAULT_DISPLAY_NAME)
    create.add_argument("--min-replicas", type=int, default=1)
    create.add_argument("--max-replicas", type=int, default=1)
    create.add_argument("--inactive-timeout", type=int, default=900)
    create.add_argument("--start", action="store_true")
    create.add_argument("--wait", action="store_true")
    create.add_argument("--wait-timeout", type=int, default=1800)

    wait = sub.add_parser("wait")
    wait.add_argument("endpoint_id")
    wait.add_argument("--timeout", type=int, default=1800)

    start = sub.add_parser("start")
    start.add_argument("endpoint_id")

    stop = sub.add_parser("stop")
    stop.add_argument("endpoint_id")

    delete = sub.add_parser("delete")
    delete.add_argument("endpoint_id")

    smoke_parser = sub.add_parser("smoke")
    smoke_parser.add_argument("--prompt", default="Write one sentence confirming this endpoint works.")
    smoke_parser.add_argument("--max-tokens", type=int, default=128)
    smoke_parser.add_argument(
        "--wait-first",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Wait for ready_replicas > 0 before calling chat (default: true).",
    )
    smoke_parser.add_argument("--wait-timeout", type=int, default=1800)

    args = parser.parse_args()
    if args.cmd == "hardware":
        list_hardware()
    elif args.cmd == "list":
        list_endpoints()
    elif args.cmd == "create":
        create_endpoint(args)
    elif args.cmd == "wait":
        wait_endpoint(args.endpoint_id, timeout=args.timeout)
    elif args.cmd == "start":
        update_state(args.endpoint_id, "STARTED")
    elif args.cmd == "stop":
        update_state(args.endpoint_id, "STOPPED")
    elif args.cmd == "delete":
        delete_endpoint(args.endpoint_id)
    elif args.cmd == "smoke":
        smoke(
            args.prompt,
            args.max_tokens,
            wait_first=args.wait_first,
            wait_timeout=args.wait_timeout,
        )
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
