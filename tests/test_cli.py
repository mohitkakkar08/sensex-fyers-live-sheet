from __future__ import annotations

from sensex_chain.cli import build_parser


def test_parser_accepts_once_for_a_manual_smoke_test() -> None:
    args = build_parser().parse_args(["--segment", "morning", "--once"])

    assert args.segment == "morning"
    assert args.once is True
