"""
APIBridge AI - Breaking Change Detection Engine
Compares two OpenAPI / Swagger specifications and categorizes changes
into BREAKING, NON_BREAKING, or COSMETIC with plain English explanations.

Pure Python logic: deterministic, fast, explainable, and zero-hallucination.
"""

from typing import Dict, Any, List, Tuple
import difflib


class ChangeSeverity:
    BREAKING = "BREAKING"
    NON_BREAKING = "NON_BREAKING"
    COSMETIC = "COSMETIC"


class ChangeType:
    ENDPOINT_REMOVED = "ENDPOINT_REMOVED"
    ENDPOINT_RENAMED = "ENDPOINT_RENAMED"
    ENDPOINT_ADDED = "ENDPOINT_ADDED"
    METHOD_REMOVED = "METHOD_REMOVED"
    PARAM_REMOVED = "PARAM_REMOVED"
    PARAM_ADDED_REQUIRED = "PARAM_ADDED_REQUIRED"
    PARAM_TYPE_CHANGED = "PARAM_TYPE_CHANGED"
    FIELD_REMOVED = "FIELD_REMOVED"
    FIELD_RENAMED = "FIELD_RENAMED"
    FIELD_TYPE_CHANGED = "FIELD_TYPE_CHANGED"
    FIELD_ADDED = "FIELD_ADDED"
    DOC_UPDATED = "DOC_UPDATED"


def extract_schema_properties(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts property definitions from an OpenAPI schema object,
    handling direct properties and basic object wrappers.
    """
    if not isinstance(schema, dict):
        return {}

    # Direct properties
    if "properties" in schema and isinstance(schema["properties"], dict):
        return schema["properties"]

    # Array items schema
    if schema.get("type") == "array" and "items" in schema and isinstance(schema["items"], dict):
        return extract_schema_properties(schema["items"])

    return {}


def get_response_schema(operation: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Safely retrieves the primary 200/201 response schema and required fields list.
    """
    responses = operation.get("responses", {})
    success_resp = responses.get("200") or responses.get("201") or responses.get(200) or responses.get(201)

    if not isinstance(success_resp, dict):
        return {}, []

    # OpenAPI 3.0: responses -> 200 -> content -> application/json -> schema
    content = success_resp.get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get("schema", {})

    # Swagger 2.0 fallback: responses -> 200 -> schema
    if not schema and "schema" in success_resp:
        schema = success_resp.get("schema", {})

    required_fields = schema.get("required", []) if isinstance(schema, dict) else []
    return schema, required_fields


def are_names_similar(name1: str, name2: str) -> bool:
    """
    Heuristic check if two names are likely renames of each other
    (e.g., 'name' and 'full_name', or '/users' and '/customers').
    """
    n1 = name1.strip("/").lower()
    n2 = name2.strip("/").lower()

    # Exact containment (e.g. 'name' in 'full_name')
    if n1 in n2 or n2 in n1:
        return True

    # High string similarity ratio
    ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
    return ratio >= 0.5


def compare_specs(old_spec: Dict[str, Any], new_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Main diffing function.
    Compares two OpenAPI contracts and returns a list of detected changes.
    """
    detected_changes: List[Dict[str, Any]] = []

    old_paths: Dict[str, Any] = old_spec.get("paths", {})
    new_paths: Dict[str, Any] = new_spec.get("paths", {})

    http_methods = ["get", "post", "put", "delete", "patch"]

    # Track endpoints for rename detection
    removed_endpoints: List[str] = [p for p in old_paths if p not in new_paths]
    added_endpoints: List[str] = [p for p in new_paths if p not in old_paths]
    matched_renames: Dict[str, str] = {}

    # Heuristic rename detection for endpoints (e.g., /users -> /customers)
    for rem in list(removed_endpoints):
        for add in list(added_endpoints):
            # Check if any HTTP methods match and response schemas match
            rem_methods = [m for m in http_methods if m in old_paths[rem]]
            add_methods = [m for m in http_methods if m in new_paths[add]]
            common_methods = set(rem_methods).intersection(set(add_methods))

            if common_methods:
                # If path names are similar or it's a 1-to-1 replacement
                if are_names_similar(rem, add) or (len(removed_endpoints) == 1 and len(added_endpoints) == 1):
                    matched_renames[rem] = add
                    removed_endpoints.remove(rem)
                    added_endpoints.remove(add)
                    break

    # Record renamed endpoints
    for old_ep, new_ep in matched_renames.items():
        detected_changes.append({
            "endpoint": old_ep,
            "method": "ANY",
            "change_type": ChangeType.ENDPOINT_RENAMED,
            "severity": ChangeSeverity.BREAKING,
            "description": f"Endpoint '{old_ep}' was renamed to '{new_ep}'. Existing client requests to '{old_ep}' will fail with 404.",
            "details": {"old_endpoint": old_ep, "new_endpoint": new_ep},
        })

    # Record completely removed endpoints
    for rem_ep in removed_endpoints:
        detected_changes.append({
            "endpoint": rem_ep,
            "method": "ALL",
            "change_type": ChangeType.ENDPOINT_REMOVED,
            "severity": ChangeSeverity.BREAKING,
            "description": f"Endpoint '{rem_ep}' was deleted. Downstream applications relying on this route will break.",
            "details": {"removed_endpoint": rem_ep},
        })

    # Record newly added endpoints
    for add_ep in added_endpoints:
        detected_changes.append({
            "endpoint": add_ep,
            "method": "ALL",
            "change_type": ChangeType.ENDPOINT_ADDED,
            "severity": ChangeSeverity.NON_BREAKING,
            "description": f"New endpoint '{add_ep}' was added. Backward compatibility is maintained.",
            "details": {"added_endpoint": add_ep},
        })

    # Compare operations across endpoints (including renamed pairs and common endpoints)
    pairs_to_check: List[Tuple[str, str]] = [(p, p) for p in old_paths if p in new_paths]
    for old_ep, new_ep in matched_renames.items():
        pairs_to_check.append((old_ep, new_ep))

    for old_path_key, new_path_key in pairs_to_check:
        old_path_item = old_paths[old_path_key]
        new_path_item = new_paths[new_path_key]

        for method in http_methods:
            if method in old_path_item and method not in new_path_item:
                detected_changes.append({
                    "endpoint": old_path_key,
                    "method": method.upper(),
                    "change_type": ChangeType.METHOD_REMOVED,
                    "severity": ChangeSeverity.BREAKING,
                    "description": f"HTTP method '{method.upper()}' was removed from endpoint '{old_path_key}'.",
                    "details": {"method": method.upper()},
                })
                continue

            if method in old_path_item and method in new_path_item:
                old_op = old_path_item[method]
                new_op = new_path_item[method]
                method_upper = method.upper()

                # 1. Compare Documentation/Summary (Cosmetic)
                old_summary = old_op.get("summary", "")
                new_summary = new_op.get("summary", "")
                if old_summary and new_summary and old_summary != new_summary:
                    detected_changes.append({
                        "endpoint": old_path_key,
                        "method": method_upper,
                        "change_type": ChangeType.DOC_UPDATED,
                        "severity": ChangeSeverity.COSMETIC,
                        "description": f"Summary updated from '{old_summary}' to '{new_summary}'. Contract logic is unchanged.",
                        "details": {"old_summary": old_summary, "new_summary": new_summary},
                    })

                # 2. Compare Query / Header Parameters
                old_params = {p.get("name"): p for p in old_op.get("parameters", []) if isinstance(p, dict)}
                new_params = {p.get("name"): p for p in new_op.get("parameters", []) if isinstance(p, dict)}

                for p_name, p_def in old_params.items():
                    if p_name not in new_params:
                        is_req = p_def.get("required", False)
                        detected_changes.append({
                            "endpoint": old_path_key,
                            "method": method_upper,
                            "change_type": ChangeType.PARAM_REMOVED,
                            "severity": ChangeSeverity.BREAKING if is_req else ChangeSeverity.NON_BREAKING,
                            "description": f"Parameter '{p_name}' was removed from {method_upper} {old_path_key}.",
                            "details": {"param_name": p_name, "required": is_req},
                        })
                    else:
                        # Check data type change
                        old_type = p_def.get("schema", {}).get("type") or p_def.get("type")
                        new_type = new_params[p_name].get("schema", {}).get("type") or new_params[p_name].get("type")
                        if old_type and new_type and old_type != new_type:
                            detected_changes.append({
                                "endpoint": old_path_key,
                                "method": method_upper,
                                "change_type": ChangeType.PARAM_TYPE_CHANGED,
                                "severity": ChangeSeverity.BREAKING,
                                "description": f"Parameter '{p_name}' data type changed from '{old_type}' to '{new_type}'.",
                                "details": {"param_name": p_name, "old_type": old_type, "new_type": new_type},
                            })

                for p_name, p_def in new_params.items():
                    if p_name not in old_params and p_def.get("required", False):
                        detected_changes.append({
                            "endpoint": old_path_key,
                            "method": method_upper,
                            "change_type": ChangeType.PARAM_ADDED_REQUIRED,
                            "severity": ChangeSeverity.BREAKING,
                            "description": f"New required parameter '{p_name}' was added to {method_upper} {new_path_key}. Existing requests missing this parameter will be rejected.",
                            "details": {"param_name": p_name, "required": True},
                        })

                # 3. Compare Response Schema Properties
                old_schema, _ = get_response_schema(old_op)
                new_schema, _ = get_response_schema(new_op)

                old_props = extract_schema_properties(old_schema)
                new_props = extract_schema_properties(new_schema)

                if old_props and new_props:
                    removed_props = [p for p in old_props if p not in new_props]
                    added_props = [p for p in new_props if p not in old_props]
                    matched_field_renames = {}

                    # Heuristic check for renamed fields (e.g. 'name' -> 'full_name')
                    for rem_f in list(removed_props):
                        for add_f in list(added_props):
                            if are_names_similar(rem_f, add_f) or (len(removed_props) == 1 and len(added_props) == 1):
                                matched_field_renames[rem_f] = add_f
                                removed_props.remove(rem_f)
                                added_props.remove(add_f)
                                break

                    for old_f, new_f in matched_field_renames.items():
                        detected_changes.append({
                            "endpoint": old_path_key,
                            "method": method_upper,
                            "change_type": ChangeType.FIELD_RENAMED,
                            "severity": ChangeSeverity.BREAKING,
                            "description": f"Response field '{old_f}' was renamed to '{new_f}'. Downstream clients parsing response['{old_f}'] will throw a KeyError.",
                            "details": {
                                "old_field": old_f,
                                "new_field": new_f,
                                "old_endpoint": old_path_key,
                                "new_endpoint": new_path_key,
                            },
                        })

                    for rem_f in removed_props:
                        detected_changes.append({
                            "endpoint": old_path_key,
                            "method": method_upper,
                            "change_type": ChangeType.FIELD_REMOVED,
                            "severity": ChangeSeverity.BREAKING,
                            "description": f"Response field '{rem_f}' was removed from {method_upper} response.",
                            "details": {"field": rem_f},
                        })

                    for add_f in added_props:
                        detected_changes.append({
                            "endpoint": old_path_key,
                            "method": method_upper,
                            "change_type": ChangeType.FIELD_ADDED,
                            "severity": ChangeSeverity.NON_BREAKING,
                            "description": f"New response field '{add_f}' was added to {method_upper} response.",
                            "details": {"field": add_f},
                        })

                    # Check for data type modifications in common fields
                    for common_f in old_props:
                        if common_f in new_props:
                            old_t = old_props[common_f].get("type")
                            new_t = new_props[common_f].get("type")
                            if old_t and new_t and old_t != new_t:
                                detected_changes.append({
                                    "endpoint": old_path_key,
                                    "method": method_upper,
                                    "change_type": ChangeType.FIELD_TYPE_CHANGED,
                                    "severity": ChangeSeverity.BREAKING,
                                    "description": f"Response field '{common_f}' type changed from '{old_t}' to '{new_t}'.",
                                    "details": {"field": common_f, "old_type": old_t, "new_type": new_t},
                                })

    return detected_changes
