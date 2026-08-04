from __future__ import annotations

from datetime import datetime

from sensex_chain.timebox import KOLKATA, SessionSegment, seconds_remaining


def test_afternoon_segment_ends_at_1530_india_time() -> None:
    now = datetime(2026, 8, 4, 12, 20, tzinfo=KOLKATA)

    assert SessionSegment.AFTERNOON.ends_at(now) == datetime(2026, 8, 4, 15, 30, tzinfo=KOLKATA)


def test_wait_seconds_is_zero_after_segment_end() -> None:
    after_close = datetime(2026, 8, 4, 15, 31, tzinfo=KOLKATA)

    assert seconds_remaining(after_close, SessionSegment.AFTERNOON) == 0


def test_segment_parser_rejects_unknown_value() -> None:
    assert SessionSegment.parse("morning") is SessionSegment.MORNING

    try:
        SessionSegment.parse("night")
    except ValueError as exc:
        assert "morning" in str(exc)
    else:
        raise AssertionError("Expected unknown segment to be rejected")
