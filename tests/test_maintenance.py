from ulpf.maintenance import run_once


class RecordingService:
    def __init__(self, files, average_bytes):
        self.files = files
        self.average_bytes = average_bytes
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        if "$files" in statement:
            return ["files", "average"], [[self.files, self.average_bytes]]
        return [], []


def test_maintenance_skips_compaction_when_file_count_is_small(monkeypatch):
    monkeypatch.setenv("ULPF_COMPACTION_MIN_FILES", "50")
    monkeypatch.setenv("ULPF_MAINTENANCE_TABLES", "application_logs")
    service = RecordingService(files=12, average_bytes=1024)
    result = run_once(service)
    assert result["compacted"] is False
    assert not any("optimize" in statement for statement in service.statements)
    assert any("expire_snapshots" in statement for statement in service.statements)
    assert any("remove_orphan_files" in statement for statement in service.statements)


def test_maintenance_compacts_only_many_small_files(monkeypatch):
    monkeypatch.setenv("ULPF_COMPACTION_MIN_FILES", "10")
    monkeypatch.setenv("ULPF_COMPACTION_TARGET_MB", "128")
    monkeypatch.setenv("ULPF_MAINTENANCE_TABLES", "application_logs")
    service = RecordingService(files=20, average_bytes=1024)
    result = run_once(service)
    assert result["compacted"] is True
    assert any("optimize" in statement for statement in service.statements)


def test_orphan_retention_has_a_three_day_floor(monkeypatch):
    monkeypatch.setenv("ULPF_ORPHAN_RETENTION_DAYS", "1")
    monkeypatch.setenv("ULPF_MAINTENANCE_TABLES", "application_logs")
    service = RecordingService(files=0, average_bytes=0)
    result = run_once(service)
    assert result["orphan_retention_days"] == 3
    assert any("retention_threshold => '3d'" in statement for statement in service.statements)


def test_maintenance_rejects_unknown_table_names(monkeypatch):
    monkeypatch.setenv("ULPF_MAINTENANCE_TABLES", "application_logs; DROP TABLE x")
    service = RecordingService(files=0, average_bytes=0)
    try:
        run_once(service)
    except ValueError as exc:
        assert "Unsupported maintenance tables" in str(exc)
    else:
        raise AssertionError("unsafe table name was accepted")
