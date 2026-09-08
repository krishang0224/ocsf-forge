import tomllib
from dataclasses import asdict
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ulpf.ui.theme_css import build_css
from ulpf.ui.theme_presets import PRESETS, Theme, contrast, foreground, from_query, mix, validated

APP = """
import streamlit as st
from ulpf.ui.theme import apply_theme
apply_theme()
st.metric('Events', 42)
st.button('Unrelated action')
"""


def test_terminal_is_flat_and_native_config_matches():
    default = PRESETS["Terminal"]
    css = build_css(default)
    assert "gradient(" not in css
    assert "--effect:none" in css
    config = tomllib.loads(Path(".streamlit/config.toml").read_text())["theme"]
    assert config["backgroundColor"].lower() == default.background
    assert config["primaryColor"].lower() == default.accent
    assert config["secondaryBackgroundColor"].lower() == mix(default.background, foreground(default.background), .055)
    assert config["font"] == default.font


@pytest.mark.parametrize("theme", PRESETS.values())
def test_presets_preserve_selectors_and_readable_text(theme):
    css = build_css(theme)
    for selector in (".status-strip", ".status-dot", ".status-dot.off", ".eyebrow", ".muted", 'div[data-testid="stMetric"]', 'button[data-baseweb="tab"]'):
        assert selector in css
    assert contrast(theme.background, foreground(theme.background)) >= 4.5
    assert contrast(theme.accent, foreground(theme.accent)) >= 4.5


def test_untrusted_url_values_cannot_inject_css():
    preset, custom = from_query({"ui_theme": "Custom", "ui_accent": "</style><script>alert(1)</script>",
                                 "ui_font": "url(https://bad.example)", "ui_radius": "1000", "ui_glow": "anything"})
    assert preset == "Custom"
    assert custom == Theme()
    assert "script>" not in build_css(custom)
    assert from_query({"ui_theme": "unknown"})[0] == "Terminal"


def test_valid_custom_values_round_trip():
    values = asdict(Theme(accent="#abcdef", background="#ffffff", font="sans", density="Spacious", radius=16, glow=True, scanlines=True))
    assert asdict(validated(values)) == values


def test_default_controls_are_collapsed_and_do_not_add_url_parameters():
    app = AppTest.from_string(APP).run()
    assert not app.exception
    assert app.expander[0].label == "Appearance"
    assert not app.expander[0].proto.expanded
    assert app.selectbox[0].value == "Terminal"
    assert not app.color_picker
    assert not app.query_params


def test_custom_survives_reruns_and_preset_switches():
    app = AppTest.from_string(APP).run()
    app.selectbox(key="forge_preset").set_value("Custom").run()
    app.color_picker(key="forge_accent").set_value("#abcdef").run()
    app.toggle(key="forge_glow").set_value(True).run()
    app.button[0].click().run()
    assert app.query_params["ui_accent"] == ["#abcdef"]
    app.selectbox(key="forge_preset").set_value("Solarized").run()
    app.selectbox(key="forge_preset").set_value("Custom").run()
    assert app.color_picker(key="forge_accent").value == "#abcdef"
    assert app.toggle(key="forge_glow").value
    assert not app.exception


def test_shared_url_initializes_controls_and_keeps_unrelated_parameters():
    app = AppTest.from_string(APP)
    app.query_params.update({"ui_theme": "Custom", "ui_accent": "#ff0000", "ui_radius": "8", "filter": "auth"})
    app.run()
    assert not app.exception
    assert app.color_picker(key="forge_accent").value == "#ff0000"
    assert app.slider(key="forge_radius").value == 8
    app.selectbox(key="forge_preset").set_value("Terminal").run()
    assert app.query_params == {"filter": ["auth"]}
