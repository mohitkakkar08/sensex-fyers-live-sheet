from __future__ import annotations

from sensex_chain.cli import build_parser


def test_parser_accepts_once_for_a_manual_smoke_test() -> None:
    args = build_parser().parse_args(["--segment", "morning", "--once"])

    assert args.segment == "morning"
    assert args.once is True


def test_parser_accepts_safe_websocket_tick_debugging() -> None:
    args = build_parser().parse_args(["--segment", "afternoon", "--debug-ticks"])

    assert args.debug_ticks is True
