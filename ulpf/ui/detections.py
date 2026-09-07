"""Read-only investigation view for local detection findings."""

import json

import streamlit as st

from ulpf.detection.sql import RECENT_DETECTIONS


@st.cache_data(ttl=10, show_spinner=False)
def _load_findings(_trino):
    return _trino.query(RECENT_DETECTIONS)[0]


def render_detections(trino) -> None:
    st.subheader("Authentication findings")
    st.caption("Rule matches are investigation leads. They do not establish that an account was compromised.")
    if st.button("Refresh findings"):
        _load_findings.clear()
    try:
        findings = _load_findings(trino)
    except Exception as exc:
        st.error("Findings could not be loaded.")
        with st.expander("Connection detail"):
            st.code(str(exc))
        return
    if findings.empty:
        st.info("No local findings stored yet. Enable the detection Compose profile and ingest authentication events. Check worker logs to confirm scans are succeeding.")
        return
    st.caption("Latest 200 stored findings. Additional findings remain available through SQL.")
    visible = ["detected_at", "title", "status", "hostname", "service_name", "ip_address", "user_id", "event_count"]
    st.dataframe(findings[visible], hide_index=True, width="stretch")
    ids = findings["event_id"].tolist()
    selected = st.selectbox("Inspect finding", ids)
    row = findings.loc[findings["event_id"] == selected].iloc[0]
    st.write(f"Rule: {row['rule_id']}")
    st.write(f"Evidence window: {row['first_seen']} to {row['last_seen']}")
    st.json(json.loads(row["evidence_event_ids_json"]))
    st.caption("Evidence IDs refer to application_logs.event_id. The OCSF document records whether this evidence list is truncated.")
    st.download_button("Download finding (OCSF JSON)", row["ocsf_json"], f"finding-{selected}.json", "application/json")
    with st.expander("OCSF finding"):
        st.json(json.loads(row["ocsf_json"]))
