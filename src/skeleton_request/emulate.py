"""
Emulation mode: replay API responses from schemas.

EmulationEnv loads .skel.json files and returns mock responses.
"""

from __future__ import annotations
import functools
import json
from pathlib import Path
from typing import Any, Callable

from .cli import EmulationSpec
from .schema import SchemaNode
from .tracing import EndpointKey, build_endpoint_key


class ResponseEmulated:
    """
    Mock response object that mimics requests.Response interface.

    Used to return fake responses in emulation mode.
    """

    def __init__(
        self,
        status_code: int,
        json_body: Any,
        headers: dict[str, str] | None = None,
    ):
        """
        Initialize emulated response.

        Args:
            status_code: HTTP status code
            json_body: Response body (JSON-compatible object)
            headers: Optional response headers
        """
        self.status_code = status_code
        self._json_body = json_body
        self.headers = headers or {"Content-Type": "application/json"}
        self.ok = 200 <= status_code < 300
        self.text = json.dumps(json_body, ensure_ascii=False)

    def json(self) -> Any:
        """Return JSON body (mimics requests.Response.json())."""
        return self._json_body

    def raise_for_status(self) -> None:
        """Raise exception for bad status codes (mimics requests.Response)."""
        if not self.ok:
            raise RuntimeError(f"Emulated HTTP error {self.status_code}")


class EmulationEnv:
    """
    Emulation environment loaded from .skel.json files.

    Provides endpoint lookup and response generation.
    """

    def __init__(self, specs: dict[EndpointKey, EmulationSpec]):
        """
        Initialize EmulationEnv.

        Args:
            specs: Dict mapping EndpointKey to EmulationSpec
        """
        self.specs = specs

    @classmethod
    def load_from_dir(cls, dir_path: str | Path) -> EmulationEnv:
        """
        Load EmulationEnv from directory containing .skel.json files.

        Args:
            dir_path: Path to directory with .skel.json files

        Returns:
            EmulationEnv instance
        """
        dir_path = Path(dir_path)
        specs = {}

        for spec_file in dir_path.glob("*.skel.json"):
            with open(spec_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                spec = EmulationSpec.from_dict(data)
                specs[spec.endpoint] = spec

        return cls(specs)

    def lookup(self, endpoint: EndpointKey) -> EmulationSpec | None:
        """
        Look up EmulationSpec for an endpoint.

        Args:
            endpoint: EndpointKey to look up

        Returns:
            EmulationSpec if found, None otherwise
        """
        return self.specs.get(endpoint)

    def get_endpoints(self) -> list[EndpointKey]:
        """Get list of all available endpoints."""
        return list(self.specs.keys())


def generate_blank_json(schema: SchemaNode) -> Any:
    """
    Generate JSON with blank/default values from schema.

    Args:
        schema: SchemaNode describing structure

    Returns:
        JSON-compatible object with dummy values
    """
    if schema.kind == "null":
        return None

    if schema.kind == "boolean":
        return False

    if schema.kind == "number":
        return 0

    if schema.kind == "string":
        return ""

    if schema.kind == "array":
        if schema.item:
            # Return array with one example item
            return [generate_blank_json(schema.item)]
        else:
            return []

    if schema.kind == "object":
        if schema.children:
            return {
                key: generate_blank_json(child)
                for key, child in schema.children.items()
            }
        else:
            return {}

    # Unknown type
    return None


def emulate(
    env: EmulationEnv,
    simulate_value: bool = False,
    llm_provider: Any = None,
    fallback_original: bool = False,
) -> Callable:
    """
    Decorator to emulate HTTP requests using EmulationEnv.

    Args:
        env: EmulationEnv with loaded specs
        simulate_value: If True, use LLM to generate realistic values
        llm_provider: LLM provider for value generation (required if simulate_value=True)
        fallback_original: If True, call original function when spec not found

    Returns:
        Decorated function

    Usage:
        @emulate(env)
        def request(method, url, **kwargs):
            return requests.request(method, url, **kwargs)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract method and URL
            method = args[0] if len(args) > 0 else kwargs.get("method")
            url = args[1] if len(args) > 1 else kwargs.get("url")

            if not method or not url:
                # Can't emulate without method/url
                if fallback_original:
                    return func(*args, **kwargs)
                raise ValueError("Cannot emulate request without method and URL")

            # Build endpoint key
            endpoint_key = build_endpoint_key(method, url, kwargs.get("params"))

            # Look up spec
            spec = env.lookup(endpoint_key)
            if not spec:
                if fallback_original:
                    return func(*args, **kwargs)
                raise RuntimeError(
                    f"No emulation spec found for {endpoint_key}. "
                    f"Available endpoints: {[str(e) for e in env.get_endpoints()]}"
                )

            # Choose status code (prefer 200, fall back to first available)
            status_code = _choose_status_code(spec)

            # Get response schema
            response_schema = spec.response_schemas_by_status.get(status_code)
            if not response_schema:
                # No schema for this status code
                json_body = {}
            elif simulate_value and llm_provider:
                # Generate values using LLM
                json_body = _generate_with_llm(
                    spec, status_code, llm_provider
                )
            else:
                # Generate blank JSON
                json_body = generate_blank_json(response_schema)

            return ResponseEmulated(
                status_code=status_code,
                json_body=json_body,
            )

        return wrapper

    return decorator


def _choose_status_code(spec: EmulationSpec) -> int:
    """
    Choose status code from EmulationSpec.

    Prefers 200, falls back to first available.
    """
    if 200 in spec.response_schemas_by_status:
        return 200

    # Fall back to first available status code
    if spec.response_schemas_by_status:
        return min(spec.response_schemas_by_status.keys())

    # No response schemas
    return 200


def _generate_with_llm(
    spec: EmulationSpec,
    status_code: int,
    llm_provider: Any,
) -> Any:
    """
    Generate realistic JSON values using LLM and type hints.

    Args:
        spec: EmulationSpec with type hints
        status_code: Status code to generate response for
        llm_provider: LLM provider

    Returns:
        JSON-compatible object with LLM-generated values
    """
    # Get schema and type hints
    response_schema = spec.response_schemas_by_status.get(status_code)
    type_hints = spec.response_type_hints.get(status_code, [])

    if not response_schema:
        return {}

    # Build prompt for LLM
    type_hints_json = json.dumps(type_hints, indent=2, ensure_ascii=False)
    prompt = f"""Generate a realistic JSON response based on this API schema.

Type hints:
{type_hints_json}

Generate a complete JSON object with realistic example values for each field.
Make values appropriate for the domain_type (e.g., valid email for "email", ISO8601 datetime for "datetime_iso8601").

Return ONLY the JSON object, no other text."""

    # Call LLM
    response_text = llm_provider._call_llm(prompt)

    # Parse JSON from response
    try:
        # Handle markdown code blocks
        json_str = response_text.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1])

        return json.loads(json_str)

    except json.JSONDecodeError:
        # Fall back to blank JSON
        return generate_blank_json(response_schema)
