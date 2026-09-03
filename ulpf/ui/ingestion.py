"""Ingestion controls and batch preview."""

import streamlit as st

from ulpf.pipeline import events_to_frame, run_pipeline
from ulpf.sample_data import SAMPLE_LOGS


def render_ingestion_controls() -> tuple[list, bool]:
    st.markdown("### Add data")
    mode = st.segmented_control("Source", ["Sample", "Upload", "Paste"], default="Sample", label_visibility="collapsed")
    lines: list[str] = []
    if mode == "Sample":
        lines = SAMPLE_LOGS
        st.caption(f"{len(lines)} representative events ready")
    elif mode == "Upload":
        upload = st.file_uploader("JSONL or log file", type=["json", "jsonl", "log", "txt"])
        if upload:
            lines = upload.read().decode("utf-8", errors="replace").splitlines()
    else:
        raw = st.text_area(
            "One event per line",
            height=180,
            placeholder='{"timestamp":"2026-01-01T10:00:00Z","level":"error","message":"..."}',
        )
        lines = raw.splitlines() if raw.strip() else []

    events = run_pipeline(lines)
    parsed = sum(event.parse_success for event in events)
    if events:
        st.caption(f"{len(events):,} events · {parsed / len(events):.0%} parsed")
    ingest = st.button("Ingest into Iceberg", type="primary", width="stretch", disabled=not events)
    return events, ingest


def render_batch_preview(events: list) -> None:
    st.subheader("Normalized batch")
    if not events:
        st.info("Choose a source in the left panel to prepare a batch.")
        return
    frame = events_to_frame(events)
    columns = [
        "timestamp",
        "severity",
        "device_product",
        "source_format",
        "src_endpoint_ip",
        "user",
        "action",
        "message",
        "parse_success",
    ]
    st.dataframe(frame[columns], width="stretch", height=420, hide_index=True)
    left, right = st.columns(2)
    left.download_button(
        "Download JSONL",
        "\n".join(event.to_json().replace("\n", "") for event in events),
        "normalized_logs.jsonl",
        "application/x-ndjson",
        width="stretch",
    )
    right.download_button("Download CSV", frame.to_csv(index=False), "normalized_logs.csv", "text/csv", width="stretch")
