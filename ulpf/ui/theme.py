"""Session-persistent appearance controls and the public styling entry point."""

from dataclasses import asdict

import streamlit as st

from ulpf.ui.theme_css import build_css
from ulpf.ui.theme_presets import FIELDS, PREFIX, PRESETS, contrast, from_query, validated


def _sync_url(preset, custom):
    desired = {} if preset == "Terminal" else {"ui_theme": preset}
    if preset == "Custom":
        desired.update({PREFIX + key: str(value).lower() if isinstance(value, bool) else str(value)
                        for key, value in asdict(custom).items()})
    for key in ("ui_theme", *(PREFIX + field for field in FIELDS)):
        if key in desired:
            if st.query_params.get(key) != desired[key]:
                st.query_params[key] = desired[key]
        elif key in st.query_params:
            del st.query_params[key]


def apply_theme() -> None:
    if "forge_custom" not in st.session_state:
        preset, custom = from_query(st.query_params)
        st.session_state.forge_preset = preset
        st.session_state.forge_custom = asdict(custom)
    custom = validated(st.session_state.forge_custom)
    with st.sidebar.expander("Appearance", expanded=False):
        preset = st.selectbox("Theme", [*PRESETS, "Custom"], key="forge_preset")
        if preset == "Custom":
            for name, value in asdict(custom).items():
                st.session_state.setdefault("forge_" + name, value)
            values = {
                "accent": st.color_picker("Accent", key="forge_accent"),
                "background": st.color_picker("Background", key="forge_background"),
                "font": st.selectbox("Font", ["monospace", "sans"], key="forge_font"),
                "density": st.selectbox("Density", ["Compact", "Comfortable", "Spacious"], key="forge_density"),
                "radius": st.slider("Corner radius", 0, 16, key="forge_radius", format="%d px"),
                "glow": st.toggle("Glow and gradients", key="forge_glow"),
                "scanlines": st.toggle("Scanline accents", key="forge_scanlines"),
            }
            custom = validated(values)
            st.session_state.forge_custom = asdict(custom)
            if contrast(custom.accent, custom.background) < 3:
                st.warning("Accent contrast is low. Choose a lighter or darker accent for readable labels and focus outlines.")
        st.caption("Copy the browser URL to share this appearance. Terminal restores the default. Native charts and table canvases keep Streamlit’s startup palette.")
    _sync_url(preset, custom)
    st.markdown(build_css(custom if preset == "Custom" else PRESETS[preset]), unsafe_allow_html=True)
