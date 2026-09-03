"""Small representative corpus used for a useful first run."""

SAMPLE_LOGS = """
<134>Jan 15 03:14:22 fw-core-01 FortiOS-100D: action=deny src=10.20.5.31 dst=203.0.113.45 sport=51244 dport=23 proto=6 deviceProduct=FortiGate msg="Telnet access attempt blocked"
<134>Jan 15 03:15:01 fw-edge-02 PaloAlto-PA220: action=allow src=172.16.8.100 dst=93.184.216.34 sport=49152 dport=443 proto=6 deviceProduct=PAN-OS msg="HTTPS session permitted"
10.14.22.101 - alice [15/Jan/2025:03:17:05 +0000] "GET /api/v1/users HTTP/1.1" 200 4821 "https://portal.example/dashboard" "Mozilla/5.0"
203.0.113.90 - - [15/Jan/2025:03:19:44 +0000] "GET /../../etc/passwd HTTP/1.1" 403 153 "-" "sqlmap/1.5"
CEF:0|CrowdStrike|FalconSensor|6.32|8001|Malware Detected|9|src=10.20.5.31 dst=10.20.5.10 suser=jdoe dhost=WS-FIN-04 act=Quarantine outcome=success fname=invoice.exe
{"timestamp":"2025-01-15T03:25:11Z","event_type":"login_success","user":"alice","src_ip":"10.14.22.101","server":"auth.internal","service":"sso","severity":"info","message":"User authenticated with MFA"}
{"timestamp":"2025-01-15T03:26:47Z","event_type":"login_failure","user":"admin","src_ip":"203.0.113.90","server":"vpn-01","service":"vpn","severity":"warning","message":"Fifth consecutive failed login"}
2025-01-15 03:28:12,105 ERROR [payment-worker] com.example.PaymentService: Card authorization timed out
""".strip().splitlines()
