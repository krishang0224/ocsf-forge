"""JSON decoding that rejects ambiguous or non-standard values."""

import json
import math


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        _constant(value)
    return result


def decode_json(value):
    decoded = json.loads(value, object_pairs_hook=_object, parse_constant=_constant, parse_float=_float)
    pending = [decoded]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            try:
                item.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("JSON contains an unpaired Unicode surrogate") from exc
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return decoded
