"""Print synthetic authentication logs that exercise all three rules."""

import json
from datetime import UTC, datetime, timedelta


def demo_logs(now: datetime | None = None, *, hostname: str = "demo-login.example") -> list[str]:
    start = (now or datetime.now(UTC)) - timedelta(minutes=2)
    attempts = [
        *[("192.0.2.10", "alice", "login_failure") for _ in range(5)],
        ("192.0.2.10", "alice", "login_success"),
        *[("192.0.2.20", f"user-{i}", "login_failure") for i in range(5)],
        *[("192.0.2.30", "bob", "login_failure") for _ in range(4)],
    ]
    return [json.dumps({
        "timestamp": (start + timedelta(seconds=index)).isoformat(),
        "event_type": action, "host": hostname, "service": "demo-identity",
        "src_ip": ip, "user": user, "message": "Synthetic authentication example",
    }, separators=(",", ":")) for index, (ip, user, action) in enumerate(attempts)]


if __name__ == "__main__":
    print("\n".join(demo_logs()))
