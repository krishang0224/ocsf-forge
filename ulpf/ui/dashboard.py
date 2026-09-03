"""Lakehouse metrics and exploratory views."""

import plotly.express as px
import streamlit as st

from ulpf.services.trino import TrinoService
from ulpf.sql import OVERVIEW_QUERY, RECENT_QUERY, SERVICE_QUERY, SEVERITY_QUERY


def render_dashboard(trino: TrinoService) -> None:
    try:
        overview, _ = trino.query(OVERVIEW_QUERY, enforce_read_only=False)
        recent, _ = trino.query(RECENT_QUERY, enforce_read_only=False)
        severity, _ = trino.query(SEVERITY_QUERY, enforce_read_only=False)
        services, _ = trino.query(SERVICE_QUERY, enforce_read_only=False)
    except Exception as exc:
        st.info("The lakehouse is starting. Once Trino and the catalog are ready, current Iceberg data appears here.")
        with st.expander("Connection detail"):
            st.code(str(exc))
        return

    row = overview.iloc[0] if not overview.empty else {}
    metrics = st.columns(4)
    metrics[0].metric("Events", f"{int(row.get('total_events', 0)):,}")
    metrics[1].metric("High / critical", f"{int(row.get('high_critical', 0)):,}")
    metrics[2].metric("Source IPs", f"{int(row.get('unique_source_ips', 0)):,}")
    metrics[3].metric("Parse rate", f"{float(row.get('parse_rate') or 0):.1f}%")

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
