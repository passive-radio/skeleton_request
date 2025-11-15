"""
Basic usage example for skeleton_request.

This example demonstrates:
1. TRACE mode: Recording API calls
2. Building emulation environment
3. EMULATE mode: Replaying API responses
"""

import requests
from skeleton_request import trace, emulate, EmulationEnv, TraceStore


# Step 1: TRACE MODE - Wrap requests with @trace decorator
@trace
def api_request(method: str, url: str, **kwargs):
    """Traced version of requests.request()."""
    return requests.request(method, url, **kwargs)


def example_trace_mode():
    """
    Example: Use TRACE mode to record API calls.

    Run this against a real API to collect schemas.
    """
    print("=== TRACE MODE ===")
    print("Making API calls to record schemas...")

    # Example API calls (replace with your actual API)
    try:
        # GET request
        response = api_request("GET", "https://jsonplaceholder.typicode.com/users/1")
        print(f"GET /users/1 -> {response.status_code}")

        # POST request
        response = api_request(
            "POST",
            "https://jsonplaceholder.typicode.com/posts",
            json={"title": "Test", "body": "Content", "userId": 1},
        )
        print(f"POST /posts -> {response.status_code}")

        # Flush traces to disk
        TraceStore.current().flush()
        trace_file = TraceStore.current().get_trace_file()
        print(f"\nTraces saved to: {trace_file}")

    except Exception as e:
        print(f"Error during tracing: {e}")


def example_build_env():
    """
    Example: Build emulation environment from traces.

    Run this after collecting traces to generate .skel.json files.
    """
    print("\n=== BUILD ENVIRONMENT ===")
    print("Run the following command to build emulation environment:")
    print("  skeleton build-env --trace-dir ./traces --output-dir ./skel_env")
    print("\nWith type inference (requires OpenAI API key):")
    print("  OPENAI_API_KEY=your-key skeleton build-env --infer-types")


def example_emulate_mode():
    """
    Example: Use EMULATE mode to replay API responses.

    Run this after building the emulation environment.
    """
    print("\n=== EMULATE MODE ===")

    try:
        # Load emulation environment
        env = EmulationEnv.load_from_dir("./skel_env")
        print(f"Loaded {len(env.get_endpoints())} endpoints")

        # Wrap requests with @emulate decorator
        @emulate(env)
        def emulated_request(method: str, url: str, **kwargs):
            return requests.request(method, url, **kwargs)

        # Make emulated API calls (no network required!)
        response = emulated_request("GET", "https://jsonplaceholder.typicode.com/users/1")
        print(f"\nEmulated GET /users/{{id}} -> {response.status_code}")
        print(f"Response: {response.json()}")

    except FileNotFoundError:
        print("Error: skel_env directory not found. Run 'skeleton build-env' first.")
    except Exception as e:
        print(f"Error during emulation: {e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python basic_usage.py trace      # Record API calls")
        print("  python basic_usage.py emulate    # Replay API responses")
        print("  python basic_usage.py build      # Show build-env command")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "trace":
        example_trace_mode()
    elif mode == "emulate":
        example_emulate_mode()
    elif mode == "build":
        example_build_env()
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
