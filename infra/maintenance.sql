-- Reference commands used by ulpf.maintenance. The scheduler first inspects
-- application_logs$files and only compacts when file-count and size thresholds fire.
ALTER TABLE iceberg.logging.application_logs
EXECUTE optimize(file_size_threshold => '128MB');

ALTER TABLE iceberg.logging.application_logs
EXECUTE expire_snapshots(retention_threshold => '7d');

ALTER TABLE iceberg.logging.application_logs
EXECUTE remove_orphan_files(retention_threshold => '7d');
