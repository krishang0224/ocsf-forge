"""Guarded Trino SQL workspace."""

import streamlit as st

from ulpf.services.backend import QueryBackend
from ulpf.sql import EXAMPLE_QUERIES


def render_sql_console(trino: QueryBackend) -> None:
    local = trino.config.backend == "duckdb"
    examples = EXAMPLE_QUERIES
    if local:
        from ulpf.services.duckdb_sql import EXAMPLES

        examples = EXAMPLES
    st.subheader("DuckDB SQL workspace" if local else "Trino SQL workspace")
    st.caption(
        "One read-only statement per run. Local file access and extension loading are disabled." if local else
        "One statement per run. Results are capped for browser safety; Iceberg data remains untouched in read-only mode."
    )
    example = st.selectbox("Start from", list(examples), label_visibility="collapsed")
    if "sql_editor" not in st.session_state:
        st.session_state.sql_editor = examples[example]
    if st.button("Load example"):
        st.session_state.sql_editor = examples[example]
    sql = st.text_area("SQL", key="sql_editor", height=220)
    if st.button("Run query", type="primary"):
        try:
            result, elapsed = trino.query(sql)
            st.success(f"Completed in {elapsed:.2f}s · {len(result):,} rows shown")
            st.dataframe(result, width="stretch", height=430, hide_index=True)
            st.download_button("Download results", result.to_csv(index=False), "trino-results.csv", "text/csv")
        except Exception as exc:
            st.error(str(exc))
