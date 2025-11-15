"""
LLM provider integration for type inference.

Supports OpenAI API-compatible providers (OpenAI, Azure OpenAI, Google Gemini).
Two modes: with_values (actual data) and key_names_only.
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from .schema import SchemaNode
from .tracing import EndpointKey


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""
    provider: str = "openai"  # "openai", "azure", "gemini"
    model: str = "gpt-5-mini"
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.0
    max_tokens: int = 2000

    @classmethod
    def from_env(cls) -> LLMConfig:
        """Load configuration from environment variables."""
        return cls(
            provider=os.getenv("SKELETON_LLM_PROVIDER", "openai"),
            model=os.getenv("SKELETON_LLM_MODEL", "gpt-5-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
            temperature=float(os.getenv("SKELETON_LLM_TEMPERATURE", "0.0")),
            max_tokens=int(os.getenv("SKELETON_LLM_MAX_TOKENS", "2000")),
        )


@dataclass
class FieldTypeInfo:
    """Type inference result for a single field."""
    path: str  # JSON path (e.g., "user.email", "items[].id")
    json_type: str  # "string", "number", "boolean", "object", "array", "null"
    domain_type: str | None = None  # "email", "datetime_iso8601", "uuid", "url", etc.
    description: str | None = None
    required: bool = True
    example_value: Any | None = None  # Only present in with_values mode


@dataclass
class TypeInferenceResult:
    """Complete type inference result for an endpoint."""
    endpoint: EndpointKey
    request_fields: list[FieldTypeInfo] = field(default_factory=list)
    response_fields: dict[int, list[FieldTypeInfo]] = field(default_factory=dict)  # status_code -> fields


class LLMProvider:
    """
    LLM provider for type inference using OpenAI-compatible API.

    Supports two modes:
    1. with_values=True: Infers types from actual data values (more accurate)
    2. with_values=False: Infers types from field names only (privacy-preserving)
    """

    def __init__(self, config: LLMConfig | None = None):
        """
        Initialize LLM provider.

        Args:
            config: LLM configuration (defaults to LLMConfig.from_env())
        """
        self.config = config or LLMConfig.from_env()

        # Initialize OpenAI client
        print(f"Base URL: {self.config.base_url}")
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

    def infer_types(
        self,
        endpoint: EndpointKey,
        request_schema: SchemaNode | None,
        response_schemas: dict[int, SchemaNode],
        request_data: Any | None = None,
        response_data_samples: dict[int, list[Any]] | None = None,
        with_values: bool = True,
    ) -> TypeInferenceResult:
        """
        Infer types for request and response fields.

        Args:
            endpoint: Endpoint key
            request_schema: Request schema
            response_schemas: Response schemas by status code
            request_data: Actual request data (optional, used if with_values=True)
            response_data_samples: Sample response data by status code
            with_values: If True, use actual values for inference; else use field names only

        Returns:
            TypeInferenceResult with inferred types
        """
        result = TypeInferenceResult(endpoint=endpoint)
        
        print(f"Inferring types for endpoint {endpoint} (with_values={with_values})...")

        # Infer request field types
        if request_schema:
            request_fields_flat = self._flatten_schema(request_schema)
            if with_values and request_data:
                result.request_fields = self._infer_with_values(request_fields_flat, request_data)
            else:
                result.request_fields = self._infer_from_names(request_fields_flat)

        # Infer response field types for each status code
        for status_code, response_schema in response_schemas.items():
            response_fields_flat = self._flatten_schema(response_schema)
            if with_values and response_data_samples and status_code in response_data_samples:
                # Use first sample for inference
                sample = response_data_samples[status_code][0] if response_data_samples[status_code] else None
                if sample:
                    result.response_fields[status_code] = self._infer_with_values(response_fields_flat, sample)
                else:
                    result.response_fields[status_code] = self._infer_from_names(response_fields_flat)
            else:
                result.response_fields[status_code] = self._infer_from_names(response_fields_flat)

        return result

    def _flatten_schema(self, schema: SchemaNode, path: str = "") -> list[tuple[str, str]]:
        """
        Flatten SchemaNode to list of (path, type) tuples.

        Args:
            schema: SchemaNode to flatten
            path: Current path prefix

        Returns:
            List of (path, json_type) tuples
        """
        results = []

        if schema.kind == "object" and schema.children:
            for key, child in schema.children.items():
                child_path = f"{path}.{key}" if path else key
                results.extend(self._flatten_schema(child, child_path))
        elif schema.kind == "array" and schema.item:
            array_path = f"{path}[]"
            results.extend(self._flatten_schema(schema.item, array_path))
        else:
            # Leaf node
            results.append((path, schema.kind))

        return results

    def _infer_with_values(self, fields: list[tuple[str, str]], data: Any) -> list[FieldTypeInfo]:
        """
        Infer types using actual data values (Mode 1).

        Args:
            fields: List of (path, json_type) tuples
            data: Actual JSON data

        Returns:
            List of FieldTypeInfo with domain types
        """
        # Prepare prompt with field paths and example values
        fields_with_values = []
        for path, json_type in fields:
            value = self._extract_value_by_path(data, path)
            fields_with_values.append({
                "path": path,
                "json_type": json_type,
                "example_value": value,
            })
        
        print(f"Preparing inference prompt with {len(fields_with_values)} fields and example values...")

        prompt = self._build_inference_prompt_with_values(fields_with_values)
        
        print(f"Calling LLM for type inference with values...")
        
        inference_results = self._call_llm(prompt)

        return self._parse_inference_results(inference_results, fields_with_values)

    def _infer_from_names(self, fields: list[tuple[str, str]]) -> list[FieldTypeInfo]:
        """
        Infer types from field names only (Mode 2).

        Args:
            fields: List of (path, json_type) tuples

        Returns:
            List of FieldTypeInfo with best-guess domain types
        """
        fields_info = [{"path": path, "json_type": json_type} for path, json_type in fields]
        
        print(f"Preparing inference prompt with {len(fields_info)} fields (names only)...")

        prompt = self._build_inference_prompt_names_only(fields_info)
        
        print(f"Calling LLM for type inference from names only...")
        
        inference_results = self._call_llm(prompt)

        return self._parse_inference_results(inference_results, fields_info)

    def _extract_value_by_path(self, data: Any, path: str) -> Any:
        """Extract value from nested data by path (e.g., 'user.email', 'items[].id')."""
        if not path:
            return data

        parts = path.replace("[]", "[0]").split(".")
        current = data

        for part in parts:
            if "[" in part:
                # Handle array access
                key, idx_str = part.split("[")
                idx = int(idx_str.rstrip("]"))
                if key:
                    current = current.get(key, [])
                if isinstance(current, list) and len(current) > idx:
                    current = current[idx]
                else:
                    return None
            else:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None

        return current

    def _build_inference_prompt_with_values(self, fields: list[dict[str, Any]]) -> str:
        """Build prompt for type inference with actual values."""
        fields_json = json.dumps(fields, indent=2, ensure_ascii=False)

        return f"""You are an API schema analyzer. Given JSON fields with their paths, types, and example values, infer the domain-specific type for each field.

Domain types include: email, url, uuid, datetime_iso8601, datetime_unix, date, time, phone_number, country_code, currency_code, amount, percentage, boolean, integer, float, text, html, markdown, json_string, base64, etc.

Input fields:
{fields_json}

For each field, provide:
1. domain_type: The most specific domain type
2. description: Brief description of what this field represents
3. required: Whether this field appears to be required (true/false)

Return a JSON array with this format:
[
  {{
    "path": "user.email",
    "domain_type": "email",
    "description": "User's email address",
    "required": true
  }},
  ...
]

Return ONLY the JSON array, no other text."""

    def _build_inference_prompt_names_only(self, fields: list[dict[str, Any]]) -> str:
        """Build prompt for type inference from field names only."""
        fields_json = json.dumps(fields, indent=2, ensure_ascii=False)

        return f"""You are an API schema analyzer. Given JSON field paths and their basic types, infer the likely domain-specific type based on naming conventions.

Domain types include: email, url, uuid, datetime_iso8601, datetime_unix, date, time, phone_number, country_code, currency_code, amount, percentage, boolean, integer, float, text, html, markdown, json_string, base64, etc.

Input fields:
{fields_json}

For each field, provide:
1. domain_type: The most likely domain type based on the field name
2. description: Brief description of what this field likely represents
3. required: Best guess whether this field is required (true/false)

Return a JSON array with this format:
[
  {{
    "path": "user.email",
    "domain_type": "email",
    "description": "Likely user's email address",
    "required": true
  }},
  ...
]

Return ONLY the JSON array, no other text."""

    def _call_llm(self, prompt: str) -> str:
        """Call LLM API and return response text."""
        self.client: OpenAI
        try:
            print(prompt)
            print(self.client.base_url, self.config.model)
            response = self.client.responses.create(
                # model=self.config.model,
                model="gpt-5-nano",
                input=[
                    {"role": "system", "content": "You are an expert API schema analyzer."},
                    {"role": "user", "content": prompt},
                ],
                timeout = 180,
                text =  { format: { type: "json_object" } },
            )
            return response.output_text or ""
        except Exception as e:
            print(f"LLM API call failed: {e}")
            return ""

    def _parse_inference_results(
        self,
        llm_response: str,
        fields_info: list[dict[str, Any]],
    ) -> list[FieldTypeInfo]:
        """Parse LLM response into FieldTypeInfo objects."""
        try:
            # Extract JSON array from response (handle markdown code blocks)
            json_str = llm_response.strip()
            if json_str.startswith("```"):
                # Remove markdown code fences
                lines = json_str.split("\n")
                json_str = "\n".join(lines[1:-1])

            results = json.loads(json_str)

            field_infos = []
            for result in results:
                # Find matching field info
                field_info = next((f for f in fields_info if f["path"] == result["path"]), None)
                if not field_info:
                    continue

                field_infos.append(
                    FieldTypeInfo(
                        path=result["path"],
                        json_type=field_info["json_type"],
                        domain_type=result.get("domain_type"),
                        description=result.get("description"),
                        required=result.get("required", True),
                        example_value=field_info.get("example_value"),
                    )
                )

            return field_infos

        except (json.JSONDecodeError, KeyError) as e:
            # Fallback: create basic FieldTypeInfo without domain types
            return [
                FieldTypeInfo(
                    path=f["path"],
                    json_type=f["json_type"],
                    example_value=f.get("example_value"),
                )
                for f in fields_info
            ]
