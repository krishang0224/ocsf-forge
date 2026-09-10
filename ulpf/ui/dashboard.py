"""Lakehouse metrics and exploratory views."""

import pandas as pd
import plotly.express as px
import streamlit as st

from ulpf.services.backend import QueryBackend
from ulpf.sql import (
    OVERVIEW_QUERY,
    QUALITY_QUERY,
    RECENT_QUERY,
    RUNS_QUERY,
    SERVICE_QUERY,
    SEVERITY_QUERY,
    WAREHOUSE_QUERY,
)


@st.cache_data(ttl=10, show_spinner=False)
def _load_dashboard(_trino: QueryBackend) -> dict[str, pd.DataFrame]:
    return _trino.query_many(
        {
            "overview": OVERVIEW_QUERY,
            "recent": RECENT_QUERY,
            "severity": SEVERITY_QUERY,
            "services": SERVICE_QUERY,
            "quality": QUALITY_QUERY,
            "runs": RUNS_QUERY,
            "warehouse": WAREHOUSE_QUERY,
        }
    )


def clear_dashboard_cache() -> None:
    _load_dashboard.clear()


def safe_parse_rate(value) -> float:
    return 0.0 if value is None or pd.isna(value) else float(value)


def render_dashboard(trino: QueryBackend) -> None:
    local = trino.config.backend == "duckdb"
    try:
        data = _load_dashboard(trino)
        overview = data["overview"]
        recent = data["recent"]
        severity = data["severity"]
        services = data["services"]
        quality = data["quality"]
        runs = data["runs"]
        warehouse = data["warehouse"]
    except Exception as exc:
        st.info("Local data could not be loaded. Check the database path and file permissions." if local else
                "The lakehouse is starting. Once Trino and the catalog are ready, current Iceberg data appears here.")
        with st.expander("Connection detail"):
            st.code(str(exc))
        return

    row = overview.iloc[0] if not overview.empty else {}
    metrics = st.columns(4)
    metrics[0].metric("Events", f"{int(row.get('total_events', 0)):,}")
    metrics[1].metric("High / critical", f"{int(row.get('high_critical', 0)):,}")
    metrics[2].metric("Source IPs", f"{int(row.get('unique_source_ips', 0)):,}")
    parse_rate = safe_parse_rate(row.get("parse_rate"))
    metrics[3].metric("Parse rate", f"{parse_rate:.1f}%")

    events_tab, ingestion_tab, warehouse_tab = st.tabs(["Events", "Ingestion quality", "Local storage" if local else "Warehouse"])
    with events_tab:
        left, right = st.columns([1, 1.65])
        with left:
            if not severity.empty:
                fig = px.pie(
                    severity,
                    names="log_level",
                    values="events",
                    hole=0.62,
                    color="log_level",
                    title="Severity mix",
                    color_discrete_map={
                        "Critical": "#ff5d73",
                        "High": "#ff9466",
                        "Medium": "#f7c65d",
                        "Low": "#62c4ff",
                        "Informational": "#41d9c2",
                    },
                )
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#cbd5e1",
                    legend_orientation="h",
                )
                st.plotly_chart(fig, width="stretch")
        with right:
            if not services.empty:
                fig = px.bar(
                    services.sort_values("events"),
                    x="events",
                    y="service_name",
                    orientation="h",
                    color="threats",
                    title="Volume by service",
                    color_continuous_scale=["#263d4b", "#41d9c2", "#ff6b77"],
                )
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#cbd5e1",
                    coloraxis_showscale=False,
                )
                st.plotly_chart(fig, width="stretch")
        st.subheader("Recent events")
        st.dataframe(recent, width="stretch", height=390, hide_index=True)
    with ingestion_tab:
        st.subheader("Parser coverage")
        st.dataframe(quality, width="stretch", hide_index=True)
        st.subheader("Ingestion runs")
        st.dataframe(runs, width="stretch", height=320, hide_index=True)
    with warehouse_tab:
        state = warehouse.iloc[0] if not warehouse.empty else {}
        if local:
            cards = st.columns(2)
            cards[0].metric("Database", f"{float(state.get('database_bytes', 0)) / 1048576:.2f} MB")
            cards[1].metric("Write-ahead log", f"{float(state.get('wal_bytes', 0)) / 1048576:.2f} MB")
            st.caption("DuckDB native storage. No Iceberg data files, snapshots, or lakehouse maintenance apply.")
            return
        cards = st.columns(3)
        cards[0].metric("Data files", f"{int(state.get('data_files', 0)):,}")
        cards[1].metric("Average file", f"{float(state.get('average_file_mb', 0.0)):.2f} MB")
        cards[2].metric("Snapshots", f"{int(state.get('snapshots', 0)):,}")
        st.caption(
            "Use these signals to schedule compaction and snapshot retention instead of running maintenance blindly."
        )
