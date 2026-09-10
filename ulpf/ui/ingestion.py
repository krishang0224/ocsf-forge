"""Bounded interactive ingestion and normalized batch preview."""

import json

import streamlit as st

from ulpf.config import settings
from ulpf.pipeline import events_to_frame, run_payload, run_pipeline
from ulpf.sample_data import SAMPLE_LOGS


@st.cache_data(ttl=300, show_spinner=False, max_entries=12)
def _cached_lines(lines: tuple[str, ...], source_id: str, source_name: str) -> list:
    return run_pipeline(lines, source_id=source_id, source_name=source_name)


@st.cache_data(ttl=300, show_spinner=False, max_entries=6)
def _cached_payload(payload: bytes, filename: str) -> list:
    return run_payload(payload, filename)


def render_ingestion_controls(*, local: bool = False) -> tuple[list, bool]:
    st.markdown("### Add data")
    mode = st.segmented_control("Source", ["Sample", "Upload", "Paste"], default="Sample", label_visibility="collapsed")
    events: list = []
    if mode == "Sample":
        st.caption(f"{len(SAMPLE_LOGS)} representative events ready")
        events = _cached_lines(tuple(SAMPLE_LOGS), "bundled-sample-v1", "Bundled sample")
    elif mode == "Upload":
        upload = st.file_uploader("Log document", type=["json", "jsonl", "log", "txt", "csv", "xml"])
        if upload:
            payload = upload.getvalue()
            if len(payload) > settings.max_upload_bytes:
                st.error(
                    f"Upload exceeds the {settings.max_upload_bytes / 1_048_576:.0f} MB interactive limit. "
                    + ("Split larger files before uploading." if local else "Use Kafka for larger feeds.")
                )
            else:
                events = _cached_payload(payload, upload.name)
    else:
        raw = st.text_area(
            "Paste JSON, CSV, XML, or one event per line",
            height=180,
            placeholder='{"timestamp":"2026-01-01T10:00:00Z","level":"error","message":"..."}',
        )
        payload = raw.encode()
        if len(payload) > settings.max_upload_bytes:
            st.error(f"Pasted input exceeds the {settings.max_upload_bytes / 1_048_576:.0f} MB interactive limit.")
        else:
            events = _cached_payload(payload, "Pasted events") if raw.strip() else []

    parsed = sum(event.parse_success for event in events)
    if events:
        st.caption(f"{len(events):,} events · {parsed:,} ready · {len(events) - parsed:,} quarantine")
    ingest = st.button("Ingest into DuckDB" if local else "Ingest into Iceberg", type="primary", width="stretch", disabled=not events)
    return events, ingest


def render_batch_preview(events: list) -> None:
    st.subheader("Normalized batch")
    if not events:
        st.info("Choose a source in the left panel to prepare a batch.")
        return
    frame = events_to_frame(events[:1000])
    if len(events) > 1000:
        st.caption(f"Previewing 1,000 of {len(events):,} events. Ingestion and downloads include the complete batch.")
    columns = [
        "timestamp",
        "severity",
        "device_product",
        "source_format",
        "parser_name",
        "class_name",
        "activity_name",
        "src_endpoint_ip",
        "user",
        "message",
        "parse_success",
        "parse_notes",
    ]
    st.dataframe(frame[columns], width="stretch", height=420, hide_index=True)
    if not st.button("Prepare full-batch downloads"):
        return
    frame = events_to_frame(events)
    left, right = st.columns(2)
    left.download_button(
        "Download JSONL",
        "\n".join(json.dumps(event.to_ocsf_dict(), separators=(",", ":"), default=str) for event in events),
        "normalized_logs.jsonl",
        "application/x-ndjson",
        width="stretch",
        on_click="ignore",
    )
    right.download_button("Download CSV", frame.to_csv(index=False), "normalized_logs.csv", "text/csv", width="stretch", on_click="ignore")
