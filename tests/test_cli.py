import json
import subprocess
import sys


def run(*args, payload=None):
    return subprocess.run([sys.executable, "-m", "ulpf", *args], input=payload, capture_output=True, timeout=15)


def test_offline_demo_exercises_all_rules():
    result = run("demo")
    assert result.returncode == 0, result.stderr
    findings = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(findings) == 3
    assert {item["unmapped"]["rule_id"] for item in findings} == {
        "auth.repeated_failures", "auth.password_spray", "auth.success_after_failures",
    }
    assert json.loads(result.stderr)["synthetic"]


def test_normalize_separates_valid_output_from_diagnostics():
    result = run("normalize", "-", payload=b'{"message":"valid"}\nnot a log\n')
    assert result.returncode == 1
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(records) == 1 and records[0]["metadata"]["uid"]
    summary = json.loads(result.stderr.splitlines()[-1])
    assert summary == {"events": 2, "accepted": 1, "rejected": 1}


def test_oversized_input_produces_no_partial_output():
    result = run("normalize", "-", "--max-bytes", "2", payload=b'{}\n')
    assert result.returncode == 2
    assert not result.stdout


def test_missing_file_has_actionable_error_without_traceback():
    result = run("normalize", "/nonexistent/ocsf-test-input.log")
    assert result.returncode == 2
    assert b"No such file" in result.stderr
    assert b"Traceback" not in result.stderr


def test_demo_runs_without_site_packages():
    result = subprocess.run([sys.executable, "-S", "-m", "ulpf", "demo"], capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stderr)["findings"] == 3
