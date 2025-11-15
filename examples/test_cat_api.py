"""
Cat API Trace Test Script

Tests skeleton_request tracing functionality with The Cat API.
Demonstrates two implementation patterns:
- Method 1: Function replacement (my_request)
- Method 2: Decorator on specific functions

Requires:
- CAT_API_KEY in .env.local file
- python-dotenv installed (uv sync --extra dev)

Usage:
    # Test Method 1 (function replacement)
    uv run python examples/test_cat_api.py --method1

    # Test Method 2 (decorator on functions)
    uv run python examples/test_cat_api.py --method2

    # Test both methods
    uv run python examples/test_cat_api.py --both
"""

import os
import sys
import argparse
from pathlib import Path

# Load environment variables from .env.local
try:
    from dotenv import load_dotenv
    # Load from project root .env.local
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env.local"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✓ Loaded environment from {env_file}")
    else:
        print(f"⚠ Warning: {env_file} not found")
except ImportError:
    print("⚠ Warning: python-dotenv not installed. Run: uv sync --extra dev")
    sys.exit(1)

import requests
from skeleton_request import trace, TraceStore


# ============================================================================
# Method 1: Function Replacement Pattern (README.md 方式)
# ============================================================================

@trace
def my_request(method: str, url: str, **kwargs):
    """
    Traced wrapper around requests.request().

    This is the "function replacement" pattern where you replace
    all requests.request() calls with my_request().
    """
    return requests.request(method, url, **kwargs)


def test_method1():
    """Test Method 1: Function replacement pattern."""
    print("\n" + "="*70)
    print("METHOD 1: Function Replacement Pattern")
    print("="*70)

    api_key = os.getenv("CAT_API_KEY")
    if not api_key:
        print("❌ Error: CAT_API_KEY not found in environment")
        return False

    print(f"Using API Key: {api_key[:20]}...")

    base_url = "https://api.thecatapi.com/v1"
    headers = {"x-api-key": api_key}

    try:
        # Test 1: Search for random cat images
        print("\n[1/3] Testing GET /images/search?limit=5")
        response = my_request(
            "GET",
            f"{base_url}/images/search",
            params={"limit": 5},
            headers=headers
        )
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            images = response.json()
            print(f"  ✓ Retrieved {len(images)} images")
            if images:
                print(f"  First image ID: {images[0].get('id')}")

        # Test 2: Get specific image by ID
        print("\n[2/3] Testing GET /images/{id}")
        image_id = "0XYvRd7oD"  # Example from documentation
        response = my_request(
            "GET",
            f"{base_url}/images/{image_id}",
            headers=headers
        )
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            image_data = response.json()
            print(f"  ✓ Retrieved image: {image_data.get('id')}")
            if image_data.get('breeds'):
                print(f"  Breed: {image_data['breeds'][0].get('name')}")

        # Test 3: Get breeds list
        print("\n[3/3] Testing GET /breeds")
        response = my_request(
            "GET",
            f"{base_url}/breeds",
            headers=headers
        )
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            breeds = response.json()
            print(f"  ✓ Retrieved {len(breeds)} breeds")
            if breeds:
                print(f"  First breed: {breeds[0].get('name')}")

        # Flush traces
        TraceStore.current().flush()
        trace_file = TraceStore.current().get_trace_file()
        print(f"\n✓ Method 1 completed successfully")
        print(f"  Traces saved to: {trace_file}")

        return True

    except Exception as e:
        print(f"\n❌ Error during Method 1: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# Method 2: Decorator Pattern (関数ごとにデコレータ)
# ============================================================================

@trace
def fetch_random_cat_images(limit: int = 5):
    """Fetch random cat images."""
    api_key = os.getenv("CAT_API_KEY")
    url = "https://api.thecatapi.com/v1/images/search"
    headers = {"x-api-key": api_key}
    params = {"limit": limit}

    return requests.get(url, headers=headers, params=params)


@trace
def fetch_cat_image_by_id(image_id: str):
    """Fetch specific cat image by ID."""
    api_key = os.getenv("CAT_API_KEY")
    url = f"https://api.thecatapi.com/v1/images/{image_id}"
    headers = {"x-api-key": api_key}

    return requests.get(url, headers=headers)


@trace
def fetch_cat_breeds():
    """Fetch list of cat breeds."""
    api_key = os.getenv("CAT_API_KEY")
    url = "https://api.thecatapi.com/v1/breeds"
    headers = {"x-api-key": api_key}

    return requests.get(url, headers=headers)


def test_method2():
    """Test Method 2: Decorator pattern on specific functions."""
    print("\n" + "="*70)
    print("METHOD 2: Decorator Pattern")
    print("="*70)

    api_key = os.getenv("CAT_API_KEY")
    if not api_key:
        print("❌ Error: CAT_API_KEY not found in environment")
        return False

    print(f"Using API Key: {api_key[:20]}...")

    try:
        # Test 1: Random images
        print("\n[1/3] Testing fetch_random_cat_images()")
        response = fetch_random_cat_images(limit=5)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            images = response.json()
            print(f"  ✓ Retrieved {len(images)} images")
            if images:
                print(f"  First image ID: {images[0].get('id')}")

        # Test 2: Specific image
        print("\n[2/3] Testing fetch_cat_image_by_id()")
        image_id = "0XYvRd7oD"
        response = fetch_cat_image_by_id(image_id)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            image_data = response.json()
            print(f"  ✓ Retrieved image: {image_data.get('id')}")
            if image_data.get('breeds'):
                print(f"  Breed: {image_data['breeds'][0].get('name')}")

        # Test 3: Breeds list
        print("\n[3/3] Testing fetch_cat_breeds()")
        response = fetch_cat_breeds()
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            breeds = response.json()
            print(f"  ✓ Retrieved {len(breeds)} breeds")
            if breeds:
                print(f"  First breed: {breeds[0].get('name')}")

        # Flush traces
        TraceStore.current().flush()
        trace_file = TraceStore.current().get_trace_file()
        print(f"\n✓ Method 2 completed successfully")
        print(f"  Traces saved to: {trace_file}")

        return True

    except Exception as e:
        print(f"\n❌ Error during Method 2: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Test skeleton_request tracing with The Cat API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python examples/test_cat_api.py --method1
  uv run python examples/test_cat_api.py --method2
  uv run python examples/test_cat_api.py --both

After running, use:
  skeleton build-env --trace-dir ./traces --output-dir ./skel_env
        """
    )

    parser.add_argument(
        "--method1",
        action="store_true",
        help="Test Method 1: Function replacement pattern"
    )
    parser.add_argument(
        "--method2",
        action="store_true",
        help="Test Method 2: Decorator pattern"
    )
    parser.add_argument(
        "--both",
        action="store_true",
        help="Test both methods"
    )

    args = parser.parse_args()

    # Default to both if no method specified
    if not (args.method1 or args.method2 or args.both):
        args.both = True

    print("🐱 Cat API Trace Test")
    print("="*70)

    results = []

    if args.method1 or args.both:
        # Reset TraceStore for clean test
        TraceStore.reset()
        results.append(("Method 1", test_method1()))

    if args.method2 or args.both:
        # Reset TraceStore for clean test
        TraceStore.reset()
        results.append(("Method 2", test_method2()))

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    for name, success in results:
        status = "✓ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")

    print("\nNext steps:")
    print("1. Check trace files: ls -la traces/")
    print("2. Build emulation env: skeleton build-env")
    print("3. Generate docs: skeleton gen-docs")

    return 0 if all(r[1] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
