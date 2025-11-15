"""
skeleton_request: HTTP API tracing and emulation library

Trace mode: Record API request/response structures without values
Emulate mode: Replay API responses from traced schemas
"""

__version__ = "0.1.0"

import os
from typing import Callable

# Export public API
from .schema import SchemaNode, extract_schema
from .tracing import EndpointKey, TraceRecord, trace as _trace
from .storage import TraceStore, load_all_traces, load_trace_records
from .emulate import EmulationEnv, ResponseEmulated, emulate as _emulate, generate_blank_json
from .llm import LLMConfig, LLMProvider, FieldTypeInfo
from .cli import EmulationSpec

__all__ = [
    # Core types
    "SchemaNode",
    "EndpointKey",
    "TraceRecord",
    "EmulationSpec",
    "EmulationEnv",
    "ResponseEmulated",
    "FieldTypeInfo",
    # Functions
    "extract_schema",
    "generate_blank_json",
    "load_all_traces",
    "load_trace_records",
    # Decorators
    "trace",
    "emulate",
    # Classes
    "TraceStore",
    "LLMConfig",
    "LLMProvider",
]


# Mode-aware decorators
def trace(func: Callable | None = None) -> Callable:
    """
    Trace decorator that respects SKELETON_MODE environment variable.

    Usage:
        @trace
        def request(method, url, **kwargs):
            return requests.request(method, url, **kwargs)

    Environment variables:
        SKELETON_MODE: "trace" (default) | "off"
        SKELETON_TRACE_DIR: Directory for trace files (default: ./traces)
    """
    mode = os.getenv("SKELETON_MODE", "trace")

    if mode == "off":
        # Pass-through mode
        def passthrough(f: Callable) -> Callable:
            return f
        return passthrough if func is None else passthrough(func)

    # Trace mode
    if func is None:
        return _trace
    return _trace(func)


def emulate(
    env: EmulationEnv | None = None,
    simulate_value: bool = False,
    llm_provider: LLMProvider | None = None,
    fallback_original: bool = False,
) -> Callable:
    """
    Emulate decorator that loads environment from SKELETON_ENV_DIR if not provided.

    Usage:
        # Manual env
        env = EmulationEnv.load_from_dir("./skel_env")
        @emulate(env)
        def request(method, url, **kwargs):
            return requests.request(method, url, **kwargs)

        # Auto-load from env var
        @emulate()
        def request(method, url, **kwargs):
            return requests.request(method, url, **kwargs)

    Environment variables:
        SKELETON_ENV_DIR: Directory with .skel.json files (default: ./skel_env)
    """
    if env is None:
        env_dir = os.getenv("SKELETON_ENV_DIR", "./skel_env")
        env = EmulationEnv.load_from_dir(env_dir)

    if llm_provider is None and simulate_value:
        llm_provider = LLMProvider()

    return _emulate(
        env=env,
        simulate_value=simulate_value,
        llm_provider=llm_provider,
        fallback_original=fallback_original,
    )
