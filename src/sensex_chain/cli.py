"""Command-line entry point for a scheduled data-only worker."""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime

import requests

from .auth import AuthenticationError, AutomatedFyersTokenProvider, FallbackTokenProvider, FyersTokenProvider
from .cache import LatestMarketCache
from .config import ConfigurationError, RuntimeConfig
from .instruments import FyersInstrumentCatalog, InstrumentDiscoveryError
from .sheet import GoogleSheetGateway, SheetGatewayError
from .socket import DataFeedError, FyersDataFeed
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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run:
        print(f"Diagnostic: DRY_RUN; segment={args.segment}; no FYERS or Google Sheets request will be made.")
        return 0
    try:
        config = RuntimeConfig.from_environ(os.environ)
        print("Diagnostic: CONFIGURATION_READY")
        http = requests.Session()
        catalog = FyersInstrumentCatalog.download(http)
        print("Diagnostic: INSTRUMENT_CATALOG_READY")
        gateway = GoogleSheetGateway.from_service_account_json(config.google_service_account_json, config.sheet_id)
        print("Diagnostic: GOOGLE_SHEETS_GATEWAY_READY")
        automated = AutomatedFyersTokenProvider(config, http, lambda: int(time.time()))
        fallback = FyersTokenProvider(config, http) if config.fyers_refresh_token else None
        worker = LiveChainWorker(catalog, FallbackTokenProvider(automated, fallback), lambda token: FyersDataFeed(f"{config.fyers_client_id}:{token}"), LatestMarketCache(), gateway, SystemClock(), config.flush_seconds)
        print("Diagnostic: FYERS_AUTHENTICATION_STARTING")
        result = worker.run(SessionSegment.parse(args.segment), max_cycles=1 if args.once else None)
        print("Diagnostic: WORKER_STOPPED_CLEANLY")
        return result
    except ConfigurationError as exc:
        print(f"Diagnostic: CONFIGURATION_ERROR; {exc}")
        return 2
    except (AuthenticationError, InstrumentDiscoveryError, DataFeedError, SheetGatewayError) as exc:
        print(f"Diagnostic: {exc}")
        return 3
    except Exception as exc:
        print(f"Diagnostic: UNEXPECTED_{type(exc).__name__.upper()}")
        return 3
