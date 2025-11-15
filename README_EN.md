# skeleton-request

HTTP API tracing and emulation library for offline development.

## Overview

`skeleton-request` enables you to:
1. **Trace** API calls in production/customer environments to capture request/response structures (without values)
2. **Infer** field types using LLM (supports domestic-region providers like Azure OpenAI, Google Gemini)
3. **Emulate** API responses in isolated development environments without network access

**Key Features:**
- Records only JSON structure (keys), never actual values - privacy-preserving by design
- LLM-powered type inference with two modes: value-based (accurate) and key-name-only (privacy-first)
- Supports OpenAI API-compatible providers (OpenAI, Azure OpenAI, Google Gemini)
- Generates both `.skel.json` emulation files and human-readable API documentation
- Simple decorator-based API - minimal code changes required

## Installation

```bash
# Clone repository
git clone https://github.com/yourusername/skeleton-request.git
cd skeleton-request

# Install with uv (requires Python 3.13+)
uv sync

# Or install in development mode
uv pip install -e .
```

## Quick Start

### 1. Trace Mode: Record API Calls

```python
import requests
from skeleton_request import trace

@trace
def api_request(method, url, **kwargs):
    return requests.request(method, url, **kwargs)

# Use as normal - traces are automatically saved to ./traces/
response = api_request("GET", "https://api.example.com/users/1")
```

### 2. Build Emulation Environment

```bash
# Basic build (schemas only)
skeleton build-env --trace-dir ./traces --output-dir ./skel_env

# With type inference using LLM (recommended)
export OPENAI_API_KEY=your-key
skeleton build-env --infer-types

# Privacy mode: infer from field names only (no values sent to LLM)
skeleton build-env --infer-types --key-names-only
```

### 3. Emulate Mode: Offline API Replay

```python
from skeleton_request import emulate, EmulationEnv

env = EmulationEnv.load_from_dir("./skel_env")

@emulate(env)
def api_request(method, url, **kwargs):
    return requests.request(method, url, **kwargs)

# Works offline! No network required
response = api_request("GET", "https://api.example.com/users/1")
print(response.json())  # Returns schema-based mock data
```

## Architecture

### Data Flow

1. **TRACE** → Capture API structure + actual data (temporary)
2. **AGGREGATE** → Merge schemas, run LLM type inference
3. **SAVE** → Store schemas + type hints (`.skel.json`), discard actual values
4. **EMULATE** → Replay responses from schemas

### Privacy Design

- Trace files contain actual values **temporarily** for type inference
- After `skeleton build-env --infer-types`, actual values are discarded
- Final `.skel.json` files contain **only** schemas and inferred types
- Use `--key-names-only` to avoid sending values to LLM entirely

### Endpoint Normalization

URLs are normalized to patterns:
- `/users/123` → `/users/{id}`
- `/orders/550e8400-...` → `/orders/{uuid}`
- Query parameters are tracked by key names only

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SKELETON_MODE` | `trace` \| `emulate` \| `off` | `trace` |
| `SKELETON_TRACE_DIR` | Directory for trace files | `./traces` |
| `SKELETON_ENV_DIR` | Directory for .skel.json files | `./skel_env` |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `OPENAI_BASE_URL` | Custom API base URL | - |
| `SKELETON_LLM_PROVIDER` | `openai` \| `azure` \| `gemini` | `openai` |
| `SKELETON_LLM_MODEL` | Model name | `gpt-4o-mini` |

## Advanced Usage

### Using Azure OpenAI (Domestic Region)

```bash
export SKELETON_LLM_PROVIDER=azure
export OPENAI_API_KEY=your-azure-key
export OPENAI_BASE_URL=https://your-resource.openai.azure.com/
export SKELETON_LLM_MODEL=gpt-4

skeleton build-env --infer-types
```

### Generate Realistic Values with LLM

```python
from skeleton_request import emulate, EmulationEnv, LLMProvider

env = EmulationEnv.load_from_dir("./skel_env")
llm = LLMProvider()

@emulate(env, simulate_value=True, llm_provider=llm)
def api_request(method, url, **kwargs):
    return requests.request(method, url, **kwargs)

# Responses will have realistic values (email, UUID, datetime, etc.)
response = api_request("GET", "https://api.example.com/users/1")
```

### Generate API Documentation

```bash
skeleton gen-docs --spec-dir ./skel_env --output-dir ./docs
```

Generates Markdown files with:
- Endpoint information
- Request/response field tables
- Inferred types and descriptions

## CLI Commands

### `skeleton build-env`

```bash
skeleton build-env [OPTIONS]

Options:
  --trace-dir PATH        Directory with trace files [default: ./traces]
  --output-dir PATH       Output directory [default: ./skel_env]
  --infer-types          Run LLM type inference
  --key-names-only       Infer from field names only (no values)
  --delete-traces        Delete trace files after build
```

### `skeleton gen-docs`

```bash
skeleton gen-docs [OPTIONS]

Options:
  --spec-dir PATH        Directory with .skel.json files [default: ./skel_env]
  --output-dir PATH      Output directory [default: ./docs]
```

## Development

```bash
# Install development dependencies
uv sync

# Run tests
python tests/test_schema.py
python tests/test_tracing.py

# Run example
python examples/basic_usage.py trace
```

## Project Structure

```
skeleton_request/
├── __init__.py        # Public API and mode switching
├── schema.py          # SchemaNode, extract_schema, merge
├── tracing.py         # @trace decorator, EndpointKey, TraceRecord
├── storage.py         # TraceStore, NDJSON persistence
├── llm.py             # LLMProvider, type inference
├── cli.py             # CLI commands (build-env, gen-docs)
└── emulate.py         # @emulate decorator, EmulationEnv
```

## License

MIT

## See Also

- [Full design document (Japanese)](README.md)
- [Examples](examples/README.md)
- [CLAUDE.md](CLAUDE.md) - Guide for Claude Code
