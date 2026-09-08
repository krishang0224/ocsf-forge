# Appearance

The default Terminal preset uses a neutral dark palette, one mint accent, monospace typography, compact spacing, 2 px corners, and no gradients or glow. The collapsed **Appearance** sidebar expander is the only additional UI on first load.

Presets: Terminal, Solarized (dark teal), High Contrast (black/yellow), and Cyberpunk (purple, rounded, subtle glow). Custom exposes accent/background, monospace or sans font, three density levels, 0–16 px corners, glow/gradients, and scanlines. Low accent contrast produces a warning; foreground and button text are derived for contrast.

Settings survive Streamlit reruns and switching away from Custom. Copy the browser URL to share a preset or custom appearance. Only validated `ui_*` appearance keys are read; unrelated query parameters are preserved. Selecting Terminal removes appearance parameters. URLs initialize new sessions; changing the URL in place without starting a new session does not override active widget state. This is session/URL persistence, not an account or device preference store.

## Integration

No `app.py` change is required. Keep `apply_theme()` after `st.set_page_config()` and before other rendering.

- `ulpf/ui/theme.py`: sidebar controls, session state, URL synchronization, unchanged public entry point.
- `ulpf/ui/theme_presets.py`: immutable preset definitions, validation, contrast and color helpers; no Streamlit dependency.
- `ulpf/ui/theme_css.py`: CSS generation and Streamlit selector compatibility, isolated so DOM upgrades do not affect preference logic.
- `.streamlit/config.toml`: native widget baseline matching Terminal. Server settings are unchanged; restart Streamlit after changing the native configuration.

## Tradeoffs

- CSS variables drive existing classes and DOM widgets. `.status-dot`, `.status-dot.off`, `.eyebrow`, `.muted`, metrics, and tab selectors retain their roles. Icon fonts are not globally overwritten.
- Streamlit canvas dataframes and Plotly figures are not DOM text and do not fully inherit injected CSS. They keep the native/startup palette or their existing chart settings; density changes do not alter dataframe row heights. Custom light backgrounds are therefore a mixed-palette experience, not a full native light theme.
- The selected font covers DOM text and inputs; code remains monospace. Native dataframe font follows the startup monospace setting, not the per-session font selector.
- Streamlit does not expose runtime native theming through a public per-session API. Rewriting global config on each selection would affect other users, so the implementation deliberately avoids that.
- Data-test and BaseWeb selectors are framework internals. Interaction tests protect persistence and validation; recheck visual styling when upgrading Streamlit.
- Effects are static and opt-in. Reduced-motion and forced-color preferences disable shadows and scanlines. Custom low-contrast accents are warned about rather than silently replaced.

Validation: `pytest -q tests/test_theme.py` covers defaults, native config alignment, compatibility selectors, URL sanitization, Custom persistence, shared settings, and unrelated query parameters.
