"""Structural storage contract used by the UI; no driver imports."""

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

import pandas as pd

from ulpf.config import Settings
from ulpf.models import IngestionResult, NormalizedEvent


class UnsafeQueryError(ValueError):
    """A statement exceeds the console's allowed operations."""


@runtime_checkable
class QueryBackend(Protocol):
    config: Settings

    def health(self) -> tuple[bool, str]: ...

    def ensure_lakehouse(self) -> None: ...

    def execute(
        self, statement: str, params: list | tuple | None = None, row_limit: int | None = None,
    ) -> tuple[list[str], list[list]]: ...

    def query(self, statement: str, enforce_read_only: bool = True) -> tuple[pd.DataFrame, float]: ...

    def query_many(self, statements: dict[str, str]) -> dict[str, pd.DataFrame]: ...

    def ingest_events(self, events: Iterable[NormalizedEvent]) -> IngestionResult: ...

    def insert_events(self, events: Iterable[NormalizedEvent]) -> int: ...
