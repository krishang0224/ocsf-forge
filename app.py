"""ULPF web entrypoint. Product logic lives in the ulpf package."""

from dataclasses import replace

import streamlit as st

from ulpf.config import settings
from ulpf.services.minio import MinioService
from ulpf.services.trino import TrinoService
from ulpf.ui.dashboard import clear_dashboard_cache, render_dashboard
from ulpf.ui.ingestion import render_batch_preview, render_ingestion_controls
from ulpf.ui.sql_console import render_sql_console
from ulpf.ui.theme import apply_theme

st.set_page_config(
    page_title="ULPF Lakehouse",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()


@st.cache_resource
def services() -> tuple[TrinoService, TrinoService, TrinoService, MinioService]:
    writer = TrinoService()
    reader = TrinoService(replace(settings, trino_user=settings.trino_read_user, trino_password=""))
    dashboard = TrinoService(replace(settings, trino_user=settings.trino_dashboard_user, trino_password=""))
    return writer, reader, dashboard, MinioService()


@st.cache_data(ttl=10, show_spinner=False)
def stack_status(_trino: TrinoService, _minio: MinioService) -> tuple[tuple[bool, str], dict]:
    return _trino.health(), _minio.status()


writer, reader, dashboard, minio = services()
(trino_ready, trino_detail), minio_state = stack_status(dashboard, minio)
if trino_ready and not st.session_state.get("lakehouse_initialized"):
    try:
        writer.ensure_lakehouse()
        st.session_state["lakehouse_initialized"] = True
    except Exception as exc:
        trino_ready, trino_detail = False, str(exc)

with st.sidebar:
    st.markdown('<p class="eyebrow">Universal log pipeline</p>', unsafe_allow_html=True)
    st.markdown("## ULPF")
    st.caption("Normalize once. Query everywhere.")
    st.divider()
    events, ingest_clicked = render_ingestion_controls()
    if ingest_clicked:
        with st.spinner("Committing an atomic Iceberg snapshot…"):
            try:
                result = writer.ingest_events(events)
                st.success(
                    f"Run complete · {result.committed:,} committed · "
                    f"{result.quarantined:,} quarantined · {result.duplicates:,} duplicates skipped"
                )
                clear_dashboard_cache()
            except Exception as exc:
                st.error("Ingestion failed")
                with st.expander("Detail"):
                    st.code(str(exc))
    st.divider()
    st.markdown("### Stack")
    st.markdown(f"{'🟢' if trino_ready else '🟠'} Trino")
    st.caption(trino_detail if trino_ready else "Waiting for query engine")
    st.markdown(f"{'🟢' if minio_state['ready'] else '🟠'} MinIO")
    st.caption("Warehouse bucket available" if minio_state["ready"] else "Waiting for warehouse")

st.markdown('<p class="eyebrow">Security analytics lakehouse</p>', unsafe_allow_html=True)
st.title("Logs, normalized and queryable")
st.caption("OCSF-aligned events · Apache Iceberg snapshots · MinIO object storage · Trino SQL")

tab_data, tab_ingest, tab_sql, tab_about = st.tabs(["Current data", "Batch preview", "SQL workspace", "Architecture"])
with tab_data:
    if trino_ready:
        render_dashboard(dashboard)
    else:
        st.info("The lakehouse is starting. Current Iceberg data will appear when Trino is ready.")
with tab_ingest:
    render_batch_preview(events)
with tab_sql:
    render_sql_console(reader)
with tab_about:
    st.subheader("End-to-end data path")
    st.code(
        "Files / Kafka · JSON / Syslog / CEF / LEEF / XML / CSV\n"
        "        │\n"
        "        ▼\n"
        "Immutable raw events ─── failures ───▶ Quarantine\n"
        "        │ parser registry + OCSF validation\n"
        "        ▼\n"
        "Normalized events ─── Trino ─────▶ Lakekeeper REST Catalog\n"
        "        │                              │\n"
        "        └──── Parquet + metadata ─────▶ MinIO",
        language="text",
    )
    st.markdown(
        "Every record first enters an immutable raw table. Valid OCSF events are merged idempotently into the normalized table; failures enter quarantine with parser and validation details. Lakekeeper persists catalog state in PostgreSQL while MinIO retains Parquet and Iceberg metadata."
    )
    st.markdown("**Safety defaults**")
    st.markdown(
        f"The browser SQL workspace is read-only. It returns at most **{settings.query_row_limit:,} rows** and accepts one statement at a time. Set `ULPF_ALLOW_MUTATING_SQL=true` only in a trusted environment when analysts need DDL or DML."
    )
