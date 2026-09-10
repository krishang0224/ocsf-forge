"""Explicit local-only entry path, without importing lakehouse clients."""

import streamlit as st

from ulpf.config import Settings, settings
from ulpf.services.backend import QueryBackend
from ulpf.ui.dashboard import clear_dashboard_cache, render_dashboard
from ulpf.ui.ingestion import render_batch_preview, render_ingestion_controls
from ulpf.ui.sql_console import render_sql_console
from ulpf.ui.theme import apply_theme


@st.cache_resource
def local_backend(config: Settings) -> QueryBackend:
    from ulpf.services.duckdb_backend import DuckDBBackend

    backend = DuckDBBackend(config)
    backend.ensure_lakehouse()
    return backend


def render_homelab() -> None:
    st.set_page_config(page_title="OCSF Forge · Homelab", layout="wide", initial_sidebar_state="expanded")
    apply_theme()
    st.title("OCSF Forge · Homelab")
    st.caption("Same parsers and OCSF output. Local DuckDB storage. No external services.")
    try:
        backend = local_backend(settings)
    except ImportError:
        st.error("Homelab dependencies are missing. Install requirements-homelab.txt and restart Streamlit.")
        st.stop()
    except Exception as exc:
        st.error("Could not open local storage. No fallback backend was started.")
        st.code(str(exc))
        st.stop()

    with st.sidebar:
        st.markdown("## OCSF Forge")
        st.caption("Homelab mode · DuckDB")
        events, clicked = render_ingestion_controls(local=True)
        if clicked:
            try:
                with st.spinner("Committing local events…"):
                    result = backend.ingest_events(events)
                st.success(f"{result.committed:,} committed · {result.quarantined:,} quarantined · {result.duplicates:,} duplicates")
                clear_dashboard_cache()
            except Exception as exc:
                st.error("Local ingestion failed; event-table changes were rolled back.")
                st.code(str(exc))
        st.caption(f"Storage directory: {settings.homelab_directory}")
        st.caption("One Streamlit process owns this database. Stop it before copying a backup or opening another writer.")

    current, preview, sql, about = st.tabs(["Current data", "Batch preview", "SQL workspace", "About homelab"])
    with current:
        render_dashboard(backend)
    with preview:
        render_batch_preview(events)
    with sql:
        render_sql_console(backend)
    with about:
        st.markdown("Raw, normalized, quarantined records and ingestion runs are stored together in one local DuckDB file. Replays deduplicate by event ID; batches commit atomically.")
        st.info("Kafka, scheduled detection, Iceberg snapshots and lakehouse maintenance remain features of the unchanged Trino deployment. Homelab mode does not start those workers.")
        st.caption("Generic parsers are unchanged. Pi-hole, router, VPN and NAS exports may require source-specific field mappings; homelab mode does not add vendor parsers.")
