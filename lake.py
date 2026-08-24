"""
============================================================================
 ULPF - Persistent Parquet Lake Module
----------------------------------------------------------------------------
 Appends every normalized event to a partitioned Parquet dataset under
 ./lake/, partitioned by source_format and ingestion date.
 Events ACCUMULATE across runs (append-only, never overwritten).
 Fully offline / air-gap compatible (pyarrow local filesystem only).
============================================================================
"""

import os
import datetime as dt
from dataclasses import asdict

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.dataset as ds

LAKE_ROOT = os.environ.get("ULPF_LAKE_DIR", "./lake")


class LakeManager:
    """Append-only writer + status reader for the partitioned Parquet lake."""

    def __init__(self, root: str = LAKE_ROOT):
        self.root = root
        os.makedirs(self.root, exist_ok=True)

    # ------------------------------------------------------------------ WRITE
    def append_events(self, events: list) -> dict:
        """
        Write normalized events into the lake, partitioned by
        source_format / ingest_date. Returns a summary dict.
        """
        if not events:
            return {"written": 0, "partitions": []}

        rows = [asdict(e) for e in events]
        df = pd.DataFrame(rows)
        df["ingest_date"] = dt.datetime.now().strftime("%Y-%m-%d")

        # Ensure stable schema for parquet (fill None ports with -1 sentinel,
        # cast everything to string-safe types where needed)
        for col in ("src_endpoint_port", "dst_endpoint_port"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(-1).astype("int32")

        table = pa.Table.from_pandas(df, preserve_index=False)

        # Unique basename per batch -> append semantics, no overwrites
        batch_id = dt.datetime.now().strftime("%Y%m%dT%H%M%S%f")
        pq.write_to_dataset(
            table,
            root_path=self.root,
            partition_cols=["source_format", "ingest_date"],
            existing_data_behavior="overwrite_or_ignore",
            basename_template=f"batch-{batch_id}-{{i}}.parquet",
        )

        parts = sorted({
            f"{r.source_format}/{r.ingest_date}"
            for r in df[["source_format", "ingest_date"]].itertuples(index=False)
        })
        return {"written": len(df), "partitions": parts}

    # ------------------------------------------------------------------- READ
    def read_all(self) -> pd.DataFrame:
        """Read the entire lake into a DataFrame (empty DF if lake is empty)."""
        if not self._has_data():
            return pd.DataFrame()
        try:
            dataset = ds.dataset(self.root, format="parquet",
                                 partitioning="hive")
            return dataset.to_table().to_pandas()
        except Exception:
            return pd.DataFrame()

    # ----------------------------------------------------------------- STATUS
    def _has_data(self) -> bool:
        if not os.path.isdir(self.root):
            return False
        for _, _, files in os.walk(self.root):
            if any(f.endswith(".parquet") for f in files):
                return True
        return False

    def status(self) -> dict:
        """
        Returns {'total_events': int, 'num_partitions': int,
                 'partition_list': [str], 'size_mb': float}
        """
        if not self._has_data():
            return {"total_events": 0, "num_partitions": 0,
                    "partition_list": [], "size_mb": 0.0}

        df = self.read_all()
        size_bytes = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, fs in os.walk(self.root) for f in fs if f.endswith(".parquet")
        )
        if df.empty or "ingest_date" not in df.columns or "source_format" not in df.columns:
            return {"total_events": len(df), "num_partitions": 0,
                    "partition_list": [], "size_mb": round(size_bytes / 1e6, 2)}

        parts = sorted({
            f"{sf}/{d}" for sf, d in
            zip(df["source_format"], df["ingest_date"])
        })
        return {"total_events": int(len(df)),
                "num_partitions": len(parts),
                "partition_list": parts,
                "size_mb": round(size_bytes / 1e6, 3)}
