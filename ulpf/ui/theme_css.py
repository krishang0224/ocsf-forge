"""CSS adapter for Streamlit 1.49; native canvas widgets remain native."""

from dataclasses import asdict

from ulpf.ui.theme_presets import foreground, mix, validated


def build_css(theme):
    theme = validated(asdict(theme))
    ink = foreground(theme.background)
    panel = mix(theme.background, ink, .055)
    vertical, horizontal, gap = {"Compact": (8, 10, ".55rem"), "Comfortable": (12, 16, ".9rem"), "Spacious": (18, 22, "1.2rem")}[theme.density]
    font = 'ui-monospace, "SFMono-Regular", Consolas, "Liberation Mono", monospace' if theme.font == "monospace" else 'system-ui, -apple-system, "Segoe UI", sans-serif'
    surface = f"linear-gradient(135deg, {panel}, {mix(panel, theme.accent, .08)})" if theme.glow else "var(--panel)"
    shadow = "0 0 12px color-mix(in srgb, var(--accent) 24%, transparent)" if theme.glow else "none"
    scanlines = "repeating-linear-gradient(0deg, transparent 0px, transparent 3px, #80808012 3px, #80808012 4px)" if theme.scanlines else "none"
    return f"""
    <style>
    :root, .stApp {{
      --ink:{ink}; --muted:{mix(theme.background, ink, .7)}; --accent:{theme.accent}; --cyan:var(--accent);
      --panel:{panel}; --background:{theme.background}; --border:{mix(theme.background, ink, .28)};
      --on-accent:{foreground(theme.accent)}; --off:var(--muted); --tool-font:{font};
      --radius:{theme.radius}px; --gap:{gap}; --effect:{shadow};
    }}
    .stApp {{ background:var(--background); background-image:{scanlines}; color:var(--ink); font-family:var(--tool-font); }}
    [data-testid="stSidebar"] {{ background:var(--panel); color:var(--ink); border-right:1px solid var(--border); }}
    [data-testid="stHeader"] {{ background:var(--background); }}
    [data-testid="stHeader"] button,[data-testid="stMarkdownContainer"],[data-testid="stMetricLabel"] {{ color:var(--ink); }}
    .block-container {{ max-width:1500px; padding-top:3.75rem; padding-bottom:1.5rem; }}
    [data-testid="stVerticalBlock"] {{ gap:var(--gap); }}
    h1,h2,h3,p,label,[data-testid="stMetricValue"],[data-testid="stMetricLabel"] {{ font-family:var(--tool-font); }}
    h1,h2,h3 {{ letter-spacing:0; color:var(--ink); }}
    h1 {{ font-size:1.65rem !important; }} h2 {{ font-size:1.3rem !important; }} h3 {{ font-size:1.1rem !important; }}
    div[data-testid="stMetric"] {{ background:{surface}; border:1px solid var(--border); border-radius:var(--radius); padding:{vertical}px {horizontal}px; box-shadow:var(--effect); }}
    div[data-testid="stMetricValue"] {{ color:var(--ink); font-size:1.55rem; }}
    [data-baseweb="tab-list"] {{ gap:2px; border-bottom:1px solid var(--border); }}
    button[data-baseweb="tab"] {{ border-radius:var(--radius) var(--radius) 0 0; padding-inline:{horizontal}px; color:var(--muted); font-family:var(--tool-font); }}
    button[data-baseweb="tab"][aria-selected="true"] {{ color:var(--accent); }}
    [data-baseweb="tab-highlight"] {{ background:var(--accent); }}
    .status-strip {{ display:flex; gap:14px; align-items:center; color:var(--muted); font-size:.85rem; margin:.25rem 0 .6rem; }}
    .status-dot {{ width:8px; height:8px; display:inline-block; border-radius:50%; margin-right:7px; background:var(--accent); box-shadow:var(--effect); }}
    .status-dot.off {{ background:var(--off); box-shadow:none; }}
    .eyebrow {{ color:var(--accent); font-size:.75rem; font-weight:700; text-transform:uppercase; letter-spacing:.08em; }}
    .muted,[data-testid="stCaptionContainer"] {{ color:var(--muted); }}
    .stButton > button,.stDownloadButton > button {{ border-radius:var(--radius); font-family:var(--tool-font); border-color:var(--border); background:var(--panel); color:var(--ink); }}
    .stButton > button[kind="primary"] {{ background:var(--accent); color:var(--on-accent); border-color:var(--accent); box-shadow:var(--effect); }}
    .stButton > button[kind="primary"] [data-testid="stMarkdownContainer"] {{ color:var(--on-accent); }}
    .stButton > button:disabled {{ opacity:.5; }}
    button:focus-visible,input:focus-visible,textarea:focus-visible {{ outline:2px solid var(--accent) !important; outline-offset:2px; }}
    [data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"] > div {{ background:var(--panel); color:var(--ink); border-radius:var(--radius); border-color:var(--border); }}
    textarea,input {{ font-family:var(--tool-font) !important; color:var(--ink) !important; caret-color:var(--accent); }}
    [data-testid="stCode"],code,pre {{ font-family:ui-monospace,Consolas,monospace; font-size:.9em; }}
    [data-testid="stExpander"] {{ border-color:var(--border); border-radius:var(--radius); }}
    @media (prefers-reduced-motion:reduce),(forced-colors:active) {{
      .stApp {{ background-image:none; }}
      div[data-testid="stMetric"],.status-dot,.stButton > button {{ box-shadow:none; }}
    }}
    </style>
    """
