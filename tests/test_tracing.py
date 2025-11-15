"""
Tests for tracing module.
"""

from skeleton_request.tracing import EndpointKey, normalize_path, build_endpoint_key


def test_normalize_path_numeric_id():
    """Test path normalization for numeric IDs."""
    assert normalize_path("/users/123") == "/users/{id}"
    assert normalize_path("/users/123/posts/456") == "/users/{id}/posts/{id}"


def test_normalize_path_uuid():
    """Test path normalization for UUIDs."""
    uuid_str = "550e8400-e29b-41d4-a716-446655440000"
    result = normalize_path(f"/orders/{uuid_str}")
    expected = "/orders/" + "{uuid}"  # Using string concatenation to avoid f-string issues
    assert result == expected, f"Expected '{expected}' but got '{result}'"


def test_normalize_path_alphanumeric():
    """Test path normalization for alphanumeric IDs."""
    assert normalize_path("/items/abc123def") == "/items/{id}"
    assert normalize_path("/items/verylongid123") == "/items/{id}"


def test_normalize_path_preserves_names():
    """Test that path normalization preserves meaningful names."""
    assert normalize_path("/users") == "/users"
    assert normalize_path("/api/v1/posts") == "/api/v1/posts"


def test_build_endpoint_key():
    """Test building endpoint key from URL."""
    key = build_endpoint_key("GET", "https://api.example.com/users/123")
    assert key.method == "GET"
    assert key.path_pattern == "/users/{id}"
    assert key.query_keys == ()


def test_build_endpoint_key_with_query():
    """Test building endpoint key with query parameters."""
    key = build_endpoint_key(
        "GET",
        "https://api.example.com/users",
        params={"page": 1, "limit": 10},
    )
    assert key.method == "GET"
    assert key.path_pattern == "/users"
    assert "page" in key.query_keys
    assert "limit" in key.query_keys


def test_endpoint_key_equality():
    """Test that equivalent endpoints have equal keys."""
    key1 = build_endpoint_key("GET", "https://api.example.com/users/123")
    key2 = build_endpoint_key("GET", "https://api.example.com/users/456")
    assert key1 == key2  # Different IDs should normalize to same pattern


def test_endpoint_key_serialization():
    """Test endpoint key serialization."""
    key = build_endpoint_key("POST", "https://api.example.com/users/{id}/posts")
    data = key.to_dict()

    restored = EndpointKey.from_dict(data)
    assert restored == key


if __name__ == "__main__":
    test_normalize_path_numeric_id()
    test_normalize_path_uuid()
    test_normalize_path_alphanumeric()
    test_normalize_path_preserves_names()
    test_build_endpoint_key()
    test_build_endpoint_key_with_query()
    test_endpoint_key_equality()
    test_endpoint_key_serialization()
    print("All tests passed!")
