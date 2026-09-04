"""OCSF Forge visual styles."""

import streamlit as st


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root { --ink: #e8edf7; --muted: #8f9aae; --cyan: #41d9c2; --panel: #111827; }
        .stApp { background: #080d16; color: var(--ink); }
        [data-testid="stSidebar"] { background: #0d1420; border-right: 1px solid #202c3d; }
        [data-testid="stHeader"] { background: rgba(8,13,22,.88); }
        .block-container { max-width: 1500px; padding-top: 1.6rem; }
        h1, h2, h3 { letter-spacing: -.025em; }
        h1 { font-size: 2rem !important; }
        div[data-testid="stMetric"] { background: linear-gradient(145deg,#111a28,#0d1521); border: 1px solid #253248; border-radius: 12px; padding: 16px 18px; }
        div[data-testid="stMetricValue"] { color: #f7fbff; font-size: 1.7rem; }
        div[data-baseweb="tab-list"] { gap: 8px; border-bottom: 1px solid #233044; }
        button[data-baseweb="tab"] { border-radius: 8px 8px 0 0; padding-inline: 18px; }
        .status-strip { display:flex; gap:18px; align-items:center; color:#a9b5c7; font-size:.88rem; margin:.25rem 0 1rem; }
        .status-dot { width:8px; height:8px; display:inline-block; border-radius:50%; margin-right:7px; background:#41d9c2; box-shadow:0 0 12px #41d9c288; }
        .status-dot.off { background:#f59e6b; box-shadow:none; }
        .eyebrow { color:#41d9c2; font-size:.78rem; font-weight:700; text-transform:uppercase; letter-spacing:.13em; }
        .muted { color:#8f9aae; }
        .stButton > button { border-radius:8px; font-weight:650; }
        .stButton > button[kind="primary"] { background:#2fc9b0; color:#06110f; border-color:#2fc9b0; }
        code { font-size:.88em; }
        </style>
        """,
        unsafe_allow_html=True,
    )
