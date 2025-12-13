"""
Schema extraction and merging for JSON structures.

SchemaNode represents JSON structure without values, tracking only keys and types.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SchemaNode:
    """
    Represents JSON structure without values.

    Tracks kind (object/array/primitive), children keys, and observed type options.
    """
    kind: str  # "object" | "array" | "string" | "number" | "boolean" | "null"
    children: dict[str, SchemaNode] | None = None  # For objects
    item: SchemaNode | None = None  # For arrays (schema of array items)
    type_options: set[str] = field(default_factory=set)  # Union types (e.g., {"string", "null"})
    occurrences: int = 0  # Number of times this schema was observed

    def __post_init__(self):
        """Initialize type_options with current kind."""
        if not self.type_options:
            self.type_options = {self.kind}

    def merge(self, other: SchemaNode) -> SchemaNode:
        """
        Merge two schemas to create a union schema.

        Handles:
        - Union types (e.g., field can be string or null)
        - Nested object merging
        - Array item schema merging
        """
        # Merge type options
        merged_types = self.type_options | other.type_options

        # Determine primary kind (prefer non-null types)
        if "object" in merged_types:
            primary_kind = "object"
        elif "array" in merged_types:
            primary_kind = "array"
        elif "string" in merged_types:
            primary_kind = "string"
        elif "number" in merged_types:
            primary_kind = "number"
        elif "boolean" in merged_types:
            primary_kind = "boolean"
        else:
            primary_kind = "null"

        # Merge children for objects
        merged_children = None
        if self.children is not None or other.children is not None:
            merged_children = {}
            all_keys = set()
            if self.children:
                all_keys.update(self.children.keys())
            if other.children:
                all_keys.update(other.children.keys())

            for key in all_keys:
                self_child = self.children.get(key) if self.children else None
                other_child = other.children.get(key) if other.children else None

                if self_child and other_child:
                    merged_children[key] = self_child.merge(other_child)
                elif self_child:
                    merged_children[key] = self_child
                else:
                    merged_children[key] = other_child

        # Merge array items
        merged_item = None
        if self.item is not None and other.item is not None:
            merged_item = self.item.merge(other.item)
        elif self.item is not None:
            merged_item = self.item
        elif other.item is not None:
            merged_item = other.item

        return SchemaNode(
            kind=primary_kind,
            children=merged_children,
            item=merged_item,
            type_options=merged_types,
            occurrences=self.occurrences + other.occurrences,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize SchemaNode to JSON-compatible dict."""
        result: dict[str, Any] = {
            "kind": self.kind,
            "type_options": list(self.type_options),
            "occurrences": self.occurrences,
        }

        if self.children is not None:
            result["children"] = {k: v.to_dict() for k, v in self.children.items()}

        if self.item is not None:
            result["item"] = self.item.to_dict()

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SchemaNode:
        """Deserialize SchemaNode from JSON-compatible dict."""
        children = None
        if "children" in data and data["children"] is not None:
            children = {k: cls.from_dict(v) for k, v in data["children"].items()}

        item = None
        if "item" in data and data["item"] is not None:
            item = cls.from_dict(data["item"])

        return cls(
            kind=data["kind"],
            children=children,
            item=item,
            type_options=set(data.get("type_options", [data["kind"]])),
            occurrences=data.get("occurrences", 0),
        )


def extract_schema(obj: Any) -> SchemaNode:
    """
    Extract schema from JSON object, preserving structure but not values.

    Args:
        obj: JSON-compatible Python object (dict, list, str, int, float, bool, None)

    Returns:
        SchemaNode representing the structure
    """
    if obj is None:
        return SchemaNode(kind="null", occurrences=1)

    if isinstance(obj, bool):  # Must check before int (bool is subclass of int)
        return SchemaNode(kind="boolean", occurrences=1)

    if isinstance(obj, (int, float)):
        return SchemaNode(kind="number", occurrences=1)

    if isinstance(obj, str):
        return SchemaNode(kind="string", occurrences=1)

    if isinstance(obj, list):
        if not obj:
            # Empty array - unknown item type
            return SchemaNode(kind="array", item=None, occurrences=1)

        # Merge schemas of all items to handle heterogeneous arrays
        item_schema = extract_schema(obj[0])
        for item in obj[1:]:
            item_schema = item_schema.merge(extract_schema(item))

        return SchemaNode(kind="array", item=item_schema, occurrences=1)

    if isinstance(obj, dict):
        children = {}
        for key, value in obj.items():
            children[key] = extract_schema(value)

        return SchemaNode(kind="object", children=children, occurrences=1)

    # Unknown type - treat as string
    return SchemaNode(kind="string", occurrences=1)
