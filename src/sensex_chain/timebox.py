"""India market-session boundaries for GitHub Actions worker segments."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo


KOLKATA = ZoneInfo("Asia/Kolkata")


class SessionSegment(str, Enum):
    """The two GitHub-hosted runner windows."""

    MORNING = "morning"
    AFTERNOON = "afternoon"

    @classmethod
    def parse(cls, value: str) -> "SessionSegment":
        try:
            return cls(value.lower())
        except ValueError as exc:
            raise ValueError("segment must be one of: morning, afternoon") from exc

    def ends_at(self, now: datetime) -> datetime:
        local = now.astimezone(KOLKATA)
        hour, minute = (12, 15) if self is SessionSegment.MORNING else (15, 30)
        return local.replace(hour=hour, minute=minute, second=0, microsecond=0)


def seconds_remaining(now: datetime, segment: SessionSegment) -> float:
    """Return seconds remaining in the chosen segment, never a negative value."""

    remaining = (segment.ends_at(now) - now.astimezone(KOLKATA)).total_seconds()
    return max(0.0, remaining)
