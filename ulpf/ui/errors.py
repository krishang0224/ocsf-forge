"""Correlated server diagnostics with opt-in local debug details."""

import logging
import os
from uuid import uuid4

import streamlit as st

LOGGER = logging.getLogger(__name__)


def error_reference(exc: Exception, context: str) -> str:
    reference = uuid4().hex[:12]
    LOGGER.error("%s [error_id=%s]", context, reference, exc_info=(type(exc), exc, exc.__traceback__))
    return reference


def show_error(exc: Exception, context: str) -> str:
    reference = error_reference(exc, context)
    st.error(f"{context} Reference: {reference}")
    if os.getenv("ULPF_DEBUG_ERRORS", "").lower() == "true":
        with st.expander("Debug detail (may contain sensitive data)"):
            st.code(str(exc))
    return reference
