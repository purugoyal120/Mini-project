"""
Service to parse, validate, and store OpenAPI / Swagger specifications.
Supports JSON and YAML formats and includes dynamic mock data generation from schema definitions.
"""

import json
import yaml
from typing import Dict, Any, Tuple, Optional
from ..database.db import get_db


def parse_and_validate_spec(raw_content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parses a raw specification string (JSON or YAML).
    Returns (parsed_dict, normalized_json_string).
    """
    cleaned = raw_content.strip()
    if not cleaned:
        raise ValueError("Specification content cannot be empty.")

    parsed: Any = None

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            parsed = yaml.safe_load(cleaned)
        except Exception as e:
            raise ValueError(f"Failed to parse specification. File must be valid JSON or YAML. Error: {str(e)}")

    if not isinstance(parsed, dict):
        raise ValueError("Invalid OpenAPI format: Root element must be an object/dictionary.")

    if "paths" not in parsed:
        raise ValueError("Invalid OpenAPI specification: Missing required 'paths' section.")

    normalized_json = json.dumps(parsed, indent=2)
    return parsed, normalized_json


def save_spec_version(api_id: int, version_tag: str, raw_content: str) -> int:
    """
    Validates and stores a new specification version for a given API.
    """
    parsed_spec, normalized_json = parse_and_validate_spec(raw_content)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM apis WHERE id = ?", (api_id,))
    if not cursor.fetchone():
        conn.close()
        raise ValueError(f"API with ID {api_id} does not exist.")

    cursor.execute("SELECT id FROM spec_versions WHERE api_id = ? AND version_tag = ?", (api_id, version_tag))
    if cursor.fetchone():
        conn.close()
        raise ValueError(f"Version '{version_tag}' has already been uploaded for this API.")

    cursor.execute(
        "INSERT INTO spec_versions (api_id, version_tag, raw_spec) VALUES (?, ?, ?)",
        (api_id, version_tag, normalized_json),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def get_spec_version(version_id: int) -> Dict[str, Any]:
    """
    Retrieves a single spec version by its database ID.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, api_id, version_tag, raw_spec, created_at FROM spec_versions WHERE id = ?", (version_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise ValueError(f"Spec version {version_id} not found.")

    return dict(row)


def list_specs_for_api(api_id: int):
    """
    Lists all specification versions uploaded for an API.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, api_id, version_tag, created_at FROM spec_versions WHERE api_id = ? ORDER BY id DESC",
        (api_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def generate_mock_data_from_schema(schema: Dict[str, Any]) -> Any:
    """
    Dynamically generates realistic mock data from an arbitrary OpenAPI schema definition.
    Handles objects, properties, examples, primitive types, and arrays.
    """
    if not isinstance(schema, dict):
        return {}

    # Check for direct example
    if "example" in schema:
        return schema["example"]

    schema_type = schema.get("type", "object")

    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        result = {}
        for prop_name, prop_def in properties.items():
            if not isinstance(prop_def, dict):
                result[prop_name] = f"sample_{prop_name}"
                continue

            if "example" in prop_def:
                result[prop_name] = prop_def["example"]
            else:
                p_type = prop_def.get("type", "string")
                if p_type == "integer":
                    result[prop_name] = 101 if "id" in prop_name.lower() else 1
                elif p_type == "number":
                    result[prop_name] = 49.99
                elif p_type == "boolean":
                    result[prop_name] = True
                elif p_type == "array":
                    items_schema = prop_def.get("items", {"type": "string"})
                    result[prop_name] = [generate_mock_data_from_schema(items_schema)]
                else:
                    # Provide natural string values
                    if "name" in prop_name.lower():
                        result[prop_name] = "Sugam" if prop_name == "full_name" or prop_name == "name" else "Standard Item"
                    elif "email" in prop_name.lower():
                        result[prop_name] = "user@example.com"
                    elif "title" in prop_name.lower():
                        result[prop_name] = "Sample Title"
                    else:
                        result[prop_name] = f"Sample {prop_name}"
        return result

    elif schema_type == "array":
        items_def = schema.get("items", {})
        return [generate_mock_data_from_schema(items_def)]

    elif schema_type == "integer":
        return 1
    elif schema_type == "number":
        return 99.95
    elif schema_type == "boolean":
        return True
    else:
        return "sample_value"
