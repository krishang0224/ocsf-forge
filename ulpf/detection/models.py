"""Detection inputs and findings, independent of storage."""

from dataclasses import dataclass
from datetime import datetime

from ulpf.models import NormalizedEvent


@dataclass(frozen=True)
class AuthenticationEvent:
    event_id: str
    timestamp: datetime
    hostname: str
    service: str
    ip_address: str
    user: str
    status_id: int
    class_uid: int = 3002
    activity_id: int = 1

    @property
    def scope(self) -> tuple[str, str, str]:
        return self.hostname, self.service, self.ip_address

    @property
    def eligible(self) -> bool:
        return (
            self.class_uid == 3002 and self.activity_id == 1 and self.status_id in {1, 2}
            and all(isinstance(value, str) and value.strip() for value in (
                self.event_id, self.hostname, self.service, self.ip_address, self.user
            ))
        )


@dataclass(frozen=True)
class Detection:
    event: NormalizedEvent
    rule_id: str
    rule_version: str
    first_seen: datetime
    last_seen: datetime
    event_count: int
    evidence_ids: tuple[str, ...]

    @property
    def event_id(self) -> str:
        return self.event.event_id

    def to_ocsf_dict(self) -> dict:
        record = self.event.to_ocsf_dict()
        record["metadata"]["uid"] = self.event_id
        record["start_time"] = int(self.first_seen.timestamp() * 1000)
        record["end_time"] = int(self.last_seen.timestamp() * 1000)
        record["finding_info"].update({
            "first_seen_time": record["start_time"],
            "last_seen_time": record["end_time"],
            "created_time": record["metadata"]["logged_time"],
        })
        return record
