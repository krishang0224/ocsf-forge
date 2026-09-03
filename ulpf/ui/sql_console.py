"""Guarded Trino SQL workspace."""

import streamlit as st

from ulpf.services.trino import TrinoService
from ulpf.sql import EXAMPLE_QUERIES


def render_sql_console(trino: TrinoService) -> None:
    st.subheader("Trino SQL workspace")
    st.caption(
        "One statement per run. Results are capped for browser safety; Iceberg data remains untouched in read-only mode."
    )
    example = st.selectbox("Start from", list(EXAMPLE_QUERIES), label_visibility="collapsed")
    if "sql_editor" not in st.session_state:
        st.session_state.sql_editor = EXAMPLE_QUERIES[example]
    if st.button("Load example"):
        st.session_state.sql_editor = EXAMPLE_QUERIES[example]
    sql = st.text_area("SQL", key="sql_editor", height=220)
    if st.button("Run query", type="primary"):
        try:
            result, elapsed = trino.query(sql)
            st.success(f"Completed in {elapsed:.2f}s · {len(result):,} rows shown")
            st.dataframe(result, width="stretch", height=430, hide_index=True)
            st.download_button("Download results", result.to_csv(index=False), "trino-results.csv", "text/csv")
        except Exception as exc:
            st.error(str(exc))
