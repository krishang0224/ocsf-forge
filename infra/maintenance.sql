-- Schedule these operations during quiet periods. Tune thresholds to workload.
ALTER TABLE iceberg.logging.application_logs
EXECUTE optimize(file_size_threshold => '128MB');

ALTER TABLE iceberg.logging.application_logs
EXECUTE expire_snapshots(retention_threshold => '7d');

ALTER TABLE iceberg.logging.application_logs
EXECUTE remove_orphan_files(retention_threshold => '7d');
