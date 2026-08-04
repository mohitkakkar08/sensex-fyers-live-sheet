"""Command-line entry point for a scheduled data-only worker."""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime

import requests

from .auth import FyersTokenProvider
from .cache import LatestMarketCache
from .config import ConfigurationError, RuntimeConfig
from .instruments import FyersInstrumentCatalog
from .sheet import GoogleSheetGateway
from .socket import FyersDataFeed
from .timebox import KOLKATA, SessionSegment
from .worker import LiveChainWorker


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(KOLKATA)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stream current-expiry SENSEX options to Google Sheets")
    parser.add_argument("--segment", required=True, choices=["morning", "afternoon"])
    parser.add_argument("--dry-run", action="store_true", help="validate only the requested execution path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run:
        print(f"Dry run: segment={args.segment}; no FYERS or Google Sheets request will be made.")
        return 0
    try:
        config = RuntimeConfig.from_environ(os.environ)
        http = requests.Session()
        catalog = FyersInstrumentCatalog.download(http)
        gateway = GoogleSheetGateway.from_service_account_json(config.google_service_account_json, config.sheet_id)
        worker = LiveChainWorker(
            catalog=catalog,
            token_provider=FyersTokenProvider(config, http),
            feed_factory=lambda token: FyersDataFeed(f"{config.fyers_client_id}:{token}"),
            cache=LatestMarketCache(),
            gateway=gateway,
            clock=SystemClock(),
            flush_seconds=config.flush_seconds,
        )
        return worker.run(SessionSegment.parse(args.segment))
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}")
        return 2
    except Exception as exc:
        print(f"Worker error: {type(exc).__name__}")
        return 3
