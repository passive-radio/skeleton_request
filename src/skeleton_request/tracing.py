"""
Tracing decorator and TraceRecord implementation.

Records API calls with full request/response data for type inference.
"""

from __future__ import annotations
import re
import functools
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse, parse_qs

from .schema import SchemaNode, extract_schema


@dataclass(frozen=True)
class EndpointKey:
    """
    Unique identifier for an API endpoint.

    Uses normalized path patterns (e.g., /users/{id}) and query parameter keys.
    """
    method: str  # "GET", "POST", etc.
    path_pattern: str  # "/users/{id}/orders/{order_id}"
    query_keys: tuple[str, ...]  # ("page", "limit")

    def __str__(self) -> str:
        """String representation for logging and file naming."""
        query_str = f"?{','.join(self.query_keys)}" if self.query_keys else ""
        return f"{self.method} {self.path_pattern}{query_str}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "method": self.method,
            "path_pattern": self.path_pattern,
            "query_keys": list(self.query_keys),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EndpointKey:
        """Deserialize from JSON-compatible dict."""
        return cls(
            method=data["method"],
            path_pattern=data["path_pattern"],
            query_keys=tuple(data["query_keys"]),
        )


def normalize_path(path: str) -> str:
    """
    Normalize URL path by replacing IDs with placeholders.

    Examples:
        /users/123 -> /users/{id}
        /orders/550e8400-e29b-41d4-a716-446655440000 -> /orders/{uuid}
        /items/abc123def -> /items/{id}
    """
    # UUID pattern (8-4-4-4-12 hex digits)
    uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

    # Replace UUIDs first
    path = re.sub(uuid_pattern, "{uuid}", path, flags=re.IGNORECASE)

    # Replace numeric IDs
    path = re.sub(r"/\d+(/|$)", r"/{id}\1", path)

    # Replace alphanumeric IDs (must contain BOTH letters AND numbers, at least 6 chars)
    # This catches "abc123def" but not "users", "orders", or "items"
    path = re.sub(r"/(?=.*[0-9])(?=.*[a-zA-Z])[a-zA-Z0-9]{6,}(/|$)", r"/{id}\1", path)

    return path


def build_endpoint_key(method: str, url: str, params: dict[str, Any] | None = None) -> EndpointKey:
    """
    Build EndpointKey from HTTP method, URL, and query parameters.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: Full URL or path
        params: Query parameters dict (from requests)

    Returns:
        EndpointKey with normalized path
    """
    parsed = urlparse(url)
    normalized = normalize_path(parsed.path)

    # Extract query parameter keys
    query_keys: list[str] = []
    if params:
        query_keys.extend(params.keys())
    # Also check URL query string
    if parsed.query:
        query_keys.extend(parse_qs(parsed.query).keys())

    return EndpointKey(
        method=method.upper(),
        path_pattern=normalized,
        query_keys=tuple(sorted(set(query_keys))),
    )


@dataclass
class TraceRecord:
    """
    Single API call trace with full request/response data.

    Contains actual values for LLM type inference (values are NOT saved to .skel.json).
    """
    endpoint: EndpointKey
    timestamp: datetime
    status_code: int
    request_schema: SchemaNode | None
    response_schema: SchemaNode | None
    # Full data for type inference (will be discarded after inference)
    request_data: Any | None = None
    response_data: Any | None = None
    # Optional metadata
    elapsed_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict (includes full data)."""
        result: dict[str, Any] = {
            "endpoint": self.endpoint.to_dict(),
            "timestamp": self.timestamp.isoformat(),
            "status_code": self.status_code,
        }

        if self.request_schema:
            result["request_schema"] = self.request_schema.to_dict()
        if self.response_schema:
            result["response_schema"] = self.response_schema.to_dict()
        if self.request_data is not None:
            result["request_data"] = self.request_data
        if self.response_data is not None:
            result["response_data"] = self.response_data
        if self.elapsed_ms is not None:
            result["elapsed_ms"] = self.elapsed_ms

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceRecord:
        """Deserialize from JSON-compatible dict."""
        return cls(
            endpoint=EndpointKey.from_dict(data["endpoint"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            status_code=data["status_code"],
            request_schema=SchemaNode.from_dict(data["request_schema"]) if "request_schema" in data else None,
            response_schema=SchemaNode.from_dict(data["response_schema"]) if "response_schema" in data else None,
            request_data=data.get("request_data"),
            response_data=data.get("response_data"),
            elapsed_ms=data.get("elapsed_ms"),
        )


def trace(func: Callable) -> Callable:
    """
    Decorator to trace HTTP requests made via requests.request().

    Usage:
        @trace
        def request(method, url, **kwargs):
            return requests.request(method, url, **kwargs)

    Records endpoint, request/response schemas, and full data for type inference.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Import here to avoid circular dependency
        from .storage import TraceStore

        # Extract method and URL from args/kwargs
        method, url = _extract_method_url(args, kwargs)
        if not method or not url:
            # Can't trace without method/url
            return func(*args, **kwargs)

        endpoint_key = build_endpoint_key(method, url, kwargs.get("params"))

        # Extract request body
        req_json = None
        if "json" in kwargs:
            req_json = kwargs["json"]
        elif "data" in kwargs:
            # Try to parse data as JSON
            req_json = _try_parse_json(kwargs.get("data"))

        # Execute the actual request
        start = time.time()
        response = func(*args, **kwargs)
        elapsed = (time.time() - start) * 1000  # ms

        # Extract response body
        res_json = _try_response_json(response)

        # Build TraceRecord
        record = TraceRecord(
            endpoint=endpoint_key,
            timestamp=datetime.now(timezone.utc),
            status_code=response.status_code,
            request_schema=extract_schema(req_json) if req_json is not None else None,
            response_schema=extract_schema(res_json) if res_json is not None else None,
            request_data=req_json,
            response_data=res_json,
            elapsed_ms=elapsed,
        )

        # Add to trace store
        TraceStore.current().add(record)

        return response

    return wrapper


def _extract_method_url(args: tuple, kwargs: dict) -> tuple[str | None, str | None]:
    """Extract HTTP method and URL from requests.request() call signature."""
    # requests.request(method, url, **kwargs)
    method = args[0] if len(args) > 0 else kwargs.get("method")
    url = args[1] if len(args) > 1 else kwargs.get("url")
    return method, url


def _try_parse_json(data: Any) -> Any | None:
    """Try to parse data as JSON string, return None if not valid JSON."""
    if isinstance(data, str):
        try:
            import json
            return json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _try_response_json(response: Any) -> Any | None:
    """Try to extract JSON from response object, return None on error."""
    try:
        return response.json()
    except (ValueError, AttributeError):
        return None
