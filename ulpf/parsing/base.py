"""Parser contracts and shared decoding helpers."""

from datetime import datetime
from typing import Protocol


class LogParser(Protocol):
    name: str
    source_format: str
    version: str

    def detect(self, value: str) -> float: ...

    def parse(self, value: str, observed_at: datetime) -> dict: ...


def unescape_cef(value: str) -> str:
    """Decode the escaping shared by CEF and LEEF payload fields."""
    output: list[str] = []
    index = 0
    replacements = {"n": "\n", "r": "\r", "t": "\t", "=": "=", "|": "|", "\\": "\\"}
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            output.append(replacements.get(value[index + 1], value[index + 1]))
            index += 2
        else:
            output.append(value[index])
            index += 1
    return "".join(output)


def split_escaped(value: str, separator: str, maxsplit: int = -1) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    splits = 0
    for character in value:
        if character == separator and not escaped and (maxsplit < 0 or splits < maxsplit):
            parts.append("".join(current))
            current = []
            splits += 1
            continue
        current.append(character)
        escaped = character == "\\" and not escaped
        if character != "\\":
            escaped = False
    parts.append("".join(current))
    return parts
