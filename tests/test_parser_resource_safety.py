import subprocess
import sys


def test_large_plain_syslog_and_unterminated_escapes_finish_within_budget():
    script = r'''
from ulpf.pipeline import run_pipeline
for message in ('x' * 1_000_000, 'key="' + ('\\' * 100_000)):
    event = run_pipeline(['Jan 15 03:14:22 host app: ' + message])[0]
    assert event.parse_success
    assert event.message == message[:2000]
    assert event.original_raw_payload.endswith(message)
event = run_pipeline(['Jan 15 03:14:22 host app: src=192.0.2.1 msg="two words with \\"quotes\\"" sport=443'])[0]
assert event.src_endpoint_ip == '192.0.2.1'
assert event.src_endpoint_port == 443
assert event.metadata['msg'] == 'two words with "quotes"'
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
