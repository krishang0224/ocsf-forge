"""Validated detection settings."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DetectionSettings:
    window_seconds: int = 300
    failure_threshold: int = 5
    spray_threshold: int = 5
    lookback_seconds: int = 3600
    interval_seconds: int = 30
    max_events: int = 50000
    evidence_limit: int = 20

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            if getattr(self, name) <= 0:
                raise ValueError(f"Detection setting {name} must be positive")
        if self.failure_threshold < 2 or self.spray_threshold < 2:
            raise ValueError("Detection thresholds must be at least two")
        if self.lookback_seconds < self.window_seconds or self.lookback_seconds < self.interval_seconds:
            raise ValueError("Detection lookback must cover the window and polling interval")
        if self.evidence_limit < 2:
            raise ValueError("Evidence limit must be at least two")

    @classmethod
    def from_env(cls):
        defaults = cls()
        return cls(**{
            name: int(os.getenv(f"ULPF_DETECTION_{name.upper()}", str(getattr(defaults, name))))
            for name in cls.__dataclass_fields__
        })
