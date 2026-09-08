"""JSON decoding that rejects ambiguous or non-standard values."""

import json
import math


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
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
    return json.loads(value, object_pairs_hook=_object, parse_constant=_constant, parse_float=_float)
