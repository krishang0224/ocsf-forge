"""Validated appearance tokens, independent of Streamlit state."""

import re
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Theme:
    accent: str = "#70d6a3"
    background: str = "#101010"
    font: str = "monospace"
    density: str = "Compact"
    radius: int = 2
    glow: bool = False
    scanlines: bool = False


PRESETS = {
    "Terminal": Theme(),
    "Solarized": Theme(accent="#2aa198", background="#002b36", density="Comfortable", radius=3),
    "High Contrast": Theme(accent="#ffff00", background="#000000", radius=0),
    "Cyberpunk": Theme(accent="#e879f9", background="#140c20", font="sans", radius=10, glow=True),
}
FIELDS = tuple(Theme.__dataclass_fields__)
PREFIX = "ui_"


def validated(values: dict) -> Theme:
    result = {}
    for key in ("accent", "background"):
        value = str(values.get(key, ""))
        if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            result[key] = value.lower()
    if values.get("font") in {"monospace", "sans"}:
        result["font"] = values["font"]
    if values.get("density") in {"Compact", "Comfortable", "Spacious"}:
        result["density"] = values["density"]
    try:
        radius = int(str(values.get("radius", "")))
        if 0 <= radius <= 16:
            result["radius"] = radius
    except ValueError:
        pass
    for key in ("glow", "scanlines"):
        result[key] = str(values.get(key, "false")).lower() == "true"
    return replace(Theme(), **result)


def from_query(params):
    preset = params.get("ui_theme", "Terminal")
    if preset not in (*PRESETS, "Custom"):
        preset = "Terminal"
    return preset, validated({key: params.get(PREFIX + key) for key in FIELDS})


def luminance(color):
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


def contrast(first, second):
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def foreground(background):
    return "#ffffff" if contrast(background, "#ffffff") >= contrast(background, "#000000") else "#000000"


def mix(first, second, amount):
    return "#" + "".join(f"{round(int(first[i:i + 2], 16) * (1 - amount) + int(second[i:i + 2], 16) * amount):02x}"
                         for i in (1, 3, 5))
