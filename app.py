"""ULPF web entrypoint. Product logic lives in the ulpf package."""

import streamlit as st

from ulpf.config import settings
from ulpf.services.minio import MinioService
from ulpf.services.trino import TrinoService
from ulpf.ui.dashboard import render_dashboard
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
def services() -> tuple[TrinoService, MinioService]:
    return TrinoService(), MinioService()


trino, minio = services()
trino_ready, trino_detail = trino.health()
minio_state = minio.status()
if trino_ready:
    try:
        trino.ensure_lakehouse()
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
                written = trino.insert_events(events)
                st.success(f"Committed {written:,} events")
                st.cache_data.clear()
            except Exception as exc:
                st.error("Ingestion failed")
                with st.expander("Detail"):
                    st.code(str(exc))
    st.divider()
    st.markdown("### Stack")
    st.markdown(f"{'🟢' if trino_ready else '🟠'} Trino")
    st.caption(trino_detail if trino_ready else "Waiting for query engine")
    st.markdown(f"{'🟢' if minio_state['ready'] else '🟠'} MinIO")
    st.caption(
        f"{minio_state['objects']:,} objects · {minio_state['size_mb']:.2f} MB"
        if minio_state["ready"]
        else "Waiting for warehouse"
    )

st.markdown('<p class="eyebrow">Security analytics lakehouse</p>', unsafe_allow_html=True)
st.title("Logs, normalized and queryable")
st.caption("OCSF-aligned events · Apache Iceberg snapshots · MinIO object storage · Trino SQL")

tab_data, tab_ingest, tab_sql, tab_about = st.tabs(["Current data", "Batch preview", "SQL workspace", "Architecture"])
with tab_data:
    if trino_ready:
        render_dashboard(trino)
    else:
        st.info("The lakehouse is starting. Current Iceberg data will appear when Trino is ready.")
with tab_ingest:
    render_batch_preview(events)
with tab_sql:
    render_sql_console(trino)
with tab_about:
    st.subheader("End-to-end data path")
    st.code(
        "Raw JSON / Syslog / CEF / Access logs\n"
        "        │\n"
        "        ▼\n"
        "ULPF parser + OCSF normalizer\n"
        "        │  parameterized INSERT\n"
        "        ▼\n"
        "Apache Trino ───── metadata ─────▶ Iceberg REST Catalog\n"
        "        │                              │\n"
        "        └──── Parquet + metadata ─────▶ MinIO",
        language="text",
    )
    st.markdown(
        "The application submits normalized batches to Trino. The Iceberg connector coordinates atomic snapshots through the REST catalog and stores Parquet data and metadata in the persistent MinIO warehouse."
    )
    st.markdown("**Safety defaults**")
    st.markdown(
        f"The browser SQL workspace is read-only. It returns at most **{settings.query_row_limit:,} rows** and accepts one statement at a time. Set `ULPF_ALLOW_MUTATING_SQL=true` only in a trusted environment when analysts need DDL or DML."
    )
