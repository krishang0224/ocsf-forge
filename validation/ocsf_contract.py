"""Partial top-level checks against upstream resolved OCSF class definitions.

This is not JSON Schema validation or complete OCSF conformance validation.
"""


def check(record, contract):
    errors = []
    attributes = contract["attributes"]
    for name, definition in attributes.items():
        if definition.get("requirement") == "required" and name not in record:
            errors.append(f"missing required attribute: {name}")
    for name, value in record.items():
        if name not in attributes:
            errors.append(f"attribute not in selected base class: {name}")
            continue
        definition = attributes[name]
        kind = definition.get("type")
        if value is None:
            errors.append(f"null attribute: {name}")
        elif definition.get("is_array"):
            if not isinstance(value, list):
                errors.append(f"expected array: {name}")
        elif kind in {"integer_t", "long_t", "timestamp_t"} and type(value) is not int:
            errors.append(f"expected integer: {name}")
        elif kind == "string_t" and not isinstance(value, str):
            errors.append(f"expected string: {name}")
        elif kind == "boolean_t" and type(value) is not bool:
            errors.append(f"expected boolean: {name}")
        elif kind == "object_t" and not isinstance(value, dict):
            errors.append(f"expected object: {name}")
        enum = definition.get("enum")
        if enum and str(value) not in enum:
            errors.append(f"invalid enum: {name}={value}")
    for constraint, names in contract.get("constraints", {}).items():
        count = sum(name in record and record[name] is not None for name in names)
        if constraint == "at_least_one" and count == 0:
            errors.append(f"at_least_one required: {', '.join(names)}")
        elif constraint == "just_one" and count != 1:
            errors.append(f"just_one required: {', '.join(names)}")
        elif constraint not in {"at_least_one", "just_one"}:
            raise ValueError(f"Unsupported constraint: {constraint}")
    if all(type(record.get(name)) is int for name in ("class_uid", "activity_id", "type_uid")):
        if record["type_uid"] != record["class_uid"] * 100 + record["activity_id"]:
            errors.append("type_uid must equal class_uid * 100 + activity_id")
    metadata = record.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("version") != "1.8.0":
        errors.append("metadata.version must be 1.8.0")
    return sorted(errors)
