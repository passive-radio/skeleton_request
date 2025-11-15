"""
Tests for schema module.
"""

from skeleton_request.schema import SchemaNode, extract_schema


def test_extract_schema_primitives():
    """Test schema extraction for primitive types."""
    assert extract_schema(None).kind == "null"
    assert extract_schema(True).kind == "boolean"
    assert extract_schema(42).kind == "number"
    assert extract_schema(3.14).kind == "number"
    assert extract_schema("hello").kind == "string"


def test_extract_schema_object():
    """Test schema extraction for objects."""
    data = {
        "name": "John",
        "age": 30,
        "active": True,
    }

    schema = extract_schema(data)
    assert schema.kind == "object"
    assert schema.children is not None
    assert "name" in schema.children
    assert schema.children["name"].kind == "string"
    assert schema.children["age"].kind == "number"
    assert schema.children["active"].kind == "boolean"


def test_extract_schema_nested_object():
    """Test schema extraction for nested objects."""
    data = {
        "user": {
            "name": "John",
            "email": "john@example.com",
        },
        "count": 5,
    }

    schema = extract_schema(data)
    assert schema.kind == "object"
    assert schema.children is not None
    assert "user" in schema.children
    assert schema.children["user"].kind == "object"
    assert schema.children["user"].children is not None
    assert "name" in schema.children["user"].children
    assert "email" in schema.children["user"].children


def test_extract_schema_array():
    """Test schema extraction for arrays."""
    data = [1, 2, 3]
    schema = extract_schema(data)
    assert schema.kind == "array"
    assert schema.item is not None
    assert schema.item.kind == "number"


def test_extract_schema_array_of_objects():
    """Test schema extraction for arrays of objects."""
    data = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]

    schema = extract_schema(data)
    assert schema.kind == "array"
    assert schema.item is not None
    assert schema.item.kind == "object"
    assert schema.item.children is not None
    assert "id" in schema.item.children
    assert "name" in schema.item.children


def test_schema_merge():
    """Test merging two schemas."""
    schema1 = extract_schema({"name": "John", "age": 30})
    schema2 = extract_schema({"name": "Jane", "city": "NYC"})

    merged = schema1.merge(schema2)
    assert merged.kind == "object"
    assert merged.children is not None
    assert "name" in merged.children
    assert "age" in merged.children
    assert "city" in merged.children


def test_schema_merge_union_types():
    """Test merging schemas with different types for same field."""
    schema1 = extract_schema({"value": "text"})
    schema2 = extract_schema({"value": None})

    merged = schema1.merge(schema2)
    assert merged.children is not None
    assert "value" in merged.children
    assert "string" in merged.children["value"].type_options
    assert "null" in merged.children["value"].type_options


def test_schema_serialization():
    """Test schema serialization and deserialization."""
    original = extract_schema({
        "name": "John",
        "age": 30,
        "tags": ["python", "javascript"],
    })

    # Serialize to dict
    data = original.to_dict()
    assert isinstance(data, dict)

    # Deserialize back
    restored = SchemaNode.from_dict(data)
    assert restored.kind == original.kind
    assert restored.children is not None
    assert "name" in restored.children
    assert "age" in restored.children
    assert "tags" in restored.children


if __name__ == "__main__":
    test_extract_schema_primitives()
    test_extract_schema_object()
    test_extract_schema_nested_object()
    test_extract_schema_array()
    test_extract_schema_array_of_objects()
    test_schema_merge()
    test_schema_merge_union_types()
    test_schema_serialization()
    print("All tests passed!")
