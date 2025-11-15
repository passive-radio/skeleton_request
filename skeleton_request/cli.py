"""
CLI commands for trace aggregation, type inference, and documentation generation.

Commands:
- skeleton collect: Aggregate trace files
- skeleton build-env: Generate .skel.json files with type inference
- skeleton gen-docs: Generate API documentation
"""

from __future__ import annotations
import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .llm import LLMConfig, LLMProvider, FieldTypeInfo
from .schema import SchemaNode
from .storage import load_all_traces
from .tracing import EndpointKey, TraceRecord


@dataclass
class EmulationSpec:
    """
    Aggregated schema and type information for a single endpoint.

    This is the final output format saved to .skel.json files.
    """
    version: int
    endpoint: EndpointKey
    request_schema: SchemaNode | None
    response_schemas_by_status: dict[int, SchemaNode]
    # Type inference results (NO actual values, only inferred types)
    request_type_hints: list[dict[str, Any]] = field(default_factory=list)
    response_type_hints: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "version": self.version,
            "endpoint": self.endpoint.to_dict(),
            "request_schema": self.request_schema.to_dict() if self.request_schema else None,
            "response_schemas_by_status": {
                str(status): schema.to_dict()
                for status, schema in self.response_schemas_by_status.items()
            },
            "request_type_hints": self.request_type_hints,
            "response_type_hints": {
                str(status): hints
                for status, hints in self.response_type_hints.items()
            },
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmulationSpec:
        """Deserialize from JSON-compatible dict."""
        return cls(
            version=data["version"],
            endpoint=EndpointKey.from_dict(data["endpoint"]),
            request_schema=SchemaNode.from_dict(data["request_schema"]) if data.get("request_schema") else None,
            response_schemas_by_status={
                int(status): SchemaNode.from_dict(schema)
                for status, schema in data.get("response_schemas_by_status", {}).items()
            },
            request_type_hints=data.get("request_type_hints", []),
            response_type_hints={
                int(status): hints
                for status, hints in data.get("response_type_hints", {}).items()
            },
            meta=data.get("meta", {}),
        )


def aggregate_traces(traces: list[TraceRecord]) -> dict[EndpointKey, EmulationSpec]:
    """
    Aggregate TraceRecords by endpoint and merge schemas.

    Args:
        traces: List of TraceRecords

    Returns:
        Dict mapping EndpointKey to EmulationSpec
    """
    # Group by endpoint
    by_endpoint: dict[EndpointKey, list[TraceRecord]] = defaultdict(list)
    for trace in traces:
        by_endpoint[trace.endpoint].append(trace)

    # Aggregate each endpoint
    specs = {}
    for endpoint, endpoint_traces in by_endpoint.items():
        # Merge request schemas
        request_schema = None
        for trace in endpoint_traces:
            if trace.request_schema:
                if request_schema:
                    request_schema = request_schema.merge(trace.request_schema)
                else:
                    request_schema = trace.request_schema

        # Merge response schemas by status code
        response_schemas: dict[int, SchemaNode] = {}
        for trace in endpoint_traces:
            status = trace.status_code
            if trace.response_schema:
                if status in response_schemas:
                    response_schemas[status] = response_schemas[status].merge(trace.response_schema)
                else:
                    response_schemas[status] = trace.response_schema

        specs[endpoint] = EmulationSpec(
            version=1,
            endpoint=endpoint,
            request_schema=request_schema,
            response_schemas_by_status=response_schemas,
            meta={
                "trace_count": len(endpoint_traces),
                "status_codes": list(response_schemas.keys()),
            },
        )

    return specs


def infer_types_for_specs(
    specs: dict[EndpointKey, EmulationSpec],
    traces: list[TraceRecord],
    llm_provider: LLMProvider,
    with_values: bool = True,
) -> None:
    """
    Run type inference for all EmulationSpecs (modifies specs in-place).

    Args:
        specs: Dict of EmulationSpecs to annotate
        traces: Original TraceRecords (for actual data samples)
        llm_provider: LLM provider for inference
        with_values: If True, use actual values; else use field names only
    """
    # Group traces by endpoint for sample data
    traces_by_endpoint: dict[EndpointKey, list[TraceRecord]] = defaultdict(list)
    for trace in traces:
        traces_by_endpoint[trace.endpoint].append(trace)
    
    print(f"Running type inference on {len(specs)} endpoints...")

    for endpoint, spec in specs.items():
        endpoint_traces = traces_by_endpoint.get(endpoint, [])

        print(f"Inferring types for endpoint {endpoint} with {len(endpoint_traces)} traces...")

        # Prepare sample data
        request_data = None
        response_data_samples: dict[int, list[Any]] = defaultdict(list)

        for trace in endpoint_traces:
            if trace.request_data and request_data is None:
                request_data = trace.request_data
            if trace.response_data:
                response_data_samples[trace.status_code].append(trace.response_data)

        # Run inference
        inference_result = llm_provider.infer_types(
            endpoint=endpoint,
            request_schema=spec.request_schema,
            response_schemas=spec.response_schemas_by_status,
            request_data=request_data,
            response_data_samples=dict(response_data_samples),
            with_values=with_values,
        )

        # Convert FieldTypeInfo to dict (WITHOUT example values)
        spec.request_type_hints = [
            {
                "path": f.path,
                "json_type": f.json_type,
                "domain_type": f.domain_type,
                "description": f.description,
                "required": f.required,
            }
            for f in inference_result.request_fields
        ]

        spec.response_type_hints = {
            status: [
                {
                    "path": f.path,
                    "json_type": f.json_type,
                    "domain_type": f.domain_type,
                    "description": f.description,
                    "required": f.required,
                }
                for f in fields
            ]
            for status, fields in inference_result.response_fields.items()
        }


def save_specs(specs: dict[EndpointKey, EmulationSpec], output_dir: Path) -> None:
    """
    Save EmulationSpecs to .skel.json files.

    Args:
        specs: Dict of EmulationSpecs
        output_dir: Directory to save files
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for endpoint, spec in specs.items():
        # Generate filename from endpoint
        # e.g., "POST_users__id.skel.json"
        method = endpoint.method
        path = endpoint.path_pattern.replace("/", "_").replace("{", "").replace("}", "").strip("_")
        filename = f"{method}_{path}.skel.json"

        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(spec.to_dict(), f, indent=2, ensure_ascii=False)

        print(f"Saved {filepath}")


def generate_docs(specs: dict[EndpointKey, EmulationSpec], output_dir: Path) -> None:
    """
    Generate Markdown documentation for each endpoint.

    Args:
        specs: Dict of EmulationSpecs
        output_dir: Directory to save markdown files
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for endpoint, spec in specs.items():
        # Generate filename
        method = endpoint.method
        path = endpoint.path_pattern.replace("/", "_").replace("{", "").replace("}", "").strip("_")
        filename = f"{method}_{path}.md"

        filepath = output_dir / filename

        # Build markdown content
        lines = [
            f"# {endpoint.method} {endpoint.path_pattern}",
            "",
            "## Endpoint Information",
            f"- **Method**: {endpoint.method}",
            f"- **Path Pattern**: {endpoint.path_pattern}",
        ]

        if endpoint.query_keys:
            lines.append(f"- **Query Parameters**: {', '.join(endpoint.query_keys)}")

        lines.append(f"- **Trace Count**: {spec.meta.get('trace_count', 'N/A')}")
        lines.append("")

        # Request schema
        if spec.request_schema and spec.request_type_hints:
            lines.append("## Request Schema")
            lines.append("")
            lines.append("| Field Path | Type | Domain Type | Description | Required |")
            lines.append("|------------|------|-------------|-------------|----------|")

            for hint in spec.request_type_hints:
                path = hint["path"]
                json_type = hint["json_type"]
                domain_type = hint.get("domain_type") or "-"
                description = hint.get("description") or "-"
                required = "Yes" if hint.get("required") else "No"

                lines.append(f"| {path} | {json_type} | {domain_type} | {description} | {required} |")

            lines.append("")

        # Response schemas
        for status_code in sorted(spec.response_schemas_by_status.keys()):
            lines.append(f"## Response Schema (Status {status_code})")
            lines.append("")

            if status_code in spec.response_type_hints:
                lines.append("| Field Path | Type | Domain Type | Description | Required |")
                lines.append("|------------|------|-------------|-------------|----------|")

                for hint in spec.response_type_hints[status_code]:
                    path = hint["path"]
                    json_type = hint["json_type"]
                    domain_type = hint.get("domain_type") or "-"
                    description = hint.get("description") or "-"
                    required = "Yes" if hint.get("required") else "No"

                    lines.append(f"| {path} | {json_type} | {domain_type} | {description} | {required} |")

                lines.append("")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"Generated {filepath}")


def cmd_build_env(args: argparse.Namespace) -> int:
    """Build emulation environment from trace files."""
    trace_dir = Path(args.trace_dir)
    output_dir = Path(args.output_dir)

    if not trace_dir.exists():
        print(f"Error: Trace directory not found: {trace_dir}", file=sys.stderr)
        return 1

    print(f"Loading traces from {trace_dir}...")
    traces = load_all_traces(trace_dir)

    if not traces:
        print(f"No trace files found in {trace_dir}", file=sys.stderr)
        return 1

    print(f"Loaded {len(traces)} trace records")

    print("Aggregating traces by endpoint...")
    specs = aggregate_traces(traces)
    print(f"Found {len(specs)} unique endpoints")

    # Run type inference if requested
    if args.infer_types:
        print("Running type inference...")
        llm_config = LLMConfig.from_env()
        llm_provider = LLMProvider(llm_config)

        with_values = not args.key_names_only
        infer_types_for_specs(specs, traces, llm_provider, with_values=with_values)
        print("Type inference completed")

    print(f"Saving EmulationSpecs to {output_dir}...")
    save_specs(specs, output_dir)

    # Delete traces if requested
    if args.delete_traces:
        print("Deleting trace files...")
        for trace_file in trace_dir.glob("*.ndjson"):
            trace_file.unlink()
        print("Trace files deleted")

    return 0


def cmd_gen_docs(args: argparse.Namespace) -> int:
    """Generate documentation from EmulationSpecs."""
    spec_dir = Path(args.spec_dir)
    output_dir = Path(args.output_dir)

    if not spec_dir.exists():
        print(f"Error: Spec directory not found: {spec_dir}", file=sys.stderr)
        return 1

    # Load all .skel.json files
    specs = {}
    for spec_file in spec_dir.glob("*.skel.json"):
        with open(spec_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            spec = EmulationSpec.from_dict(data)
            specs[spec.endpoint] = spec

    if not specs:
        print(f"No .skel.json files found in {spec_dir}", file=sys.stderr)
        return 1

    print(f"Loaded {len(specs)} EmulationSpecs")
    print(f"Generating documentation to {output_dir}...")
    generate_docs(specs, output_dir)

    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="skeleton",
        description="HTTP API tracing and emulation toolkit",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # build-env command
    build_parser = subparsers.add_parser(
        "build-env",
        help="Build emulation environment from trace files",
    )
    build_parser.add_argument(
        "--trace-dir",
        default="./traces",
        help="Directory containing trace files (default: ./traces)",
    )
    build_parser.add_argument(
        "--output-dir",
        default="./skel_env",
        help="Output directory for .skel.json files (default: ./skel_env)",
    )
    build_parser.add_argument(
        "--infer-types",
        action="store_true",
        help="Run LLM type inference on schemas",
    )
    build_parser.add_argument(
        "--key-names-only",
        action="store_true",
        help="Infer types from field names only (no actual values)",
    )
    build_parser.add_argument(
        "--delete-traces",
        action="store_true",
        help="Delete trace files after building env",
    )

    # gen-docs command
    docs_parser = subparsers.add_parser(
        "gen-docs",
        help="Generate API documentation from EmulationSpecs",
    )
    docs_parser.add_argument(
        "--spec-dir",
        default="./skel_env",
        help="Directory containing .skel.json files (default: ./skel_env)",
    )
    docs_parser.add_argument(
        "--output-dir",
        default="./docs",
        help="Output directory for markdown files (default: ./docs)",
    )

    args = parser.parse_args()

    if args.command == "build-env":
        return cmd_build_env(args)
    elif args.command == "gen-docs":
        return cmd_gen_docs(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
