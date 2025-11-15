# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`skeleton-trace` is a Python library for tracing and emulating HTTP API requests. It captures API request/response structures (without values) for recreating API behavior in isolated environments where the real API is inaccessible.

**Core Concept:**
- **TRACE mode**: Wraps `requests.request` calls with `@skeleton.trace` decorator to record endpoint patterns, JSON key structures (without values), and status codes to NDJSON files
- **EMULATE mode**: Uses `@skeleton.emulate` decorator to replay API responses from traced schemas without network calls
- **LLM Integration**: Uses domestic-region LLMs for type inference and documentation generation from traced schemas

## Architecture

The implementation follows a 3-layer architecture:

1. **Tracing Layer** (`tracing.py`, `schema.py`, `storage.py`)
   - Captures API call metadata during execution
   - Builds `SchemaNode` trees representing JSON structure without values
   - Stores traces as NDJSON (1 line per TraceRecord)

2. **Aggregation & Type Inference** (`cli.py`, `llm.py`)
   - CLI tool merges multiple traces per endpoint using `SchemaNode.merge()`
   - LLM Provider abstraction for type inference (customers provide domestic LLM implementation)
   - Generates paired outputs: `.skel.json` (emulation schemas) + `.md` (API documentation)

3. **Emulation Layer** (`emulate.py`)
   - Loads `EmulationEnv` from `.skel.json` files
   - Returns `ResponseEmulated` objects mimicking `requests.Response`
   - Optional `simulate_value=True` uses lightweight LLM to generate plausible dummy values

## Key Data Structures

**EndpointKey**: Identifies unique endpoints via `(method, path_pattern, query_keys)` where path patterns normalize IDs (e.g., `/users/123` → `/users/{id}`)

**SchemaNode**: Recursive tree storing JSON structure with `kind` (object/array/string/etc.), `children`, `type_options` (for union types), and `occurrences` for merging

**TraceRecord**: Single API call snapshot with `endpoint`, `timestamp`, `status_code`, `request_schema`, `response_schema`

**EmulationSpec**: Aggregated schema per endpoint with `response_schemas_by_status` for different HTTP status codes

## Development Setup

This project uses `uv` for dependency management and requires Python 3.13+.

```bash
# Install dependencies
uv sync

# Run in development mode
uv run python -m skeleton_request
```

## Privacy & Security Design

- **NO VALUE STORAGE**: Only JSON keys, structure, and types are recorded (never actual data)
- URL hosts and headers are masked/omitted by default
- LLM receives only key names + type info (no sensitive values)
- Optional encryption for trace files in customer environments

## Implementation Roadmap (from README)

1. **MVP**: `SchemaNode` + `extract_schema` + `TraceStore` + `@trace` + NDJSON output
2. **Aggregation**: CLI to merge NDJSON → `EmulationSpec` → `.skel.json`
3. **Emulation**: `EmulationEnv` + `ResponseEmulated` + `@emulate` + blank value generation
4. **LLM Integration**: `LLMProvider` abstraction + type inference + Markdown doc generation
5. **DX**: Environment variable mode switching + logging + tests

## Mode Switching

Controlled via `SKELETON_MODE` environment variable:
- `trace`: Records API calls to NDJSON
- `emulate`: Replays from `.skel.json` files (requires `SKELETON_ENV_DIR`)
- `off`: Pass-through mode (no decoration)

## Planned CLI Commands

- `skeleton collect`: Scan and aggregate trace NDJSON files
- `skeleton build-env`: Generate `.skel.json` emulation specs
- `skeleton gen-docs`: Generate Markdown API documentation (requires LLM provider)
