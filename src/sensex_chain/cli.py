"""Command-line entry point for a scheduled data-only worker."""
from __future__ import annotations
import argparse, os, time
from datetime import datetime
import requests
from .auth import AutomatedFyersTokenProvider, FallbackTokenProvider, FyersTokenProvider
from .cache import LatestMarketCache
from .config import ConfigurationError, RuntimeConfig
from .instruments import FyersInstrumentCatalog, InstrumentDiscoveryError
from .sheet import GoogleSheetGateway
from .socket import FyersDataFeed
from .timebox import KOLKATA, SessionSegment
from .worker import LiveChainWorker
class SystemClock:
 def now(self)->datetime:return datetime.now(KOLKATA)
 def sleep(self,seconds:float)->None:time.sleep(seconds)
def build_parser()->argparse.ArgumentParser:
 p=argparse.ArgumentParser(description="Stream current-expiry SENSEX options to Google Sheets")
 p.add_argument("--segment",required=True,choices=["morning","afternoon"]); p.add_argument("--dry-run",action="store_true"); p.add_argument("--once",action="store_true"); return p
def main(argv:list[str]|None=None)->int:
 args=build_parser().parse_args(argv)
 if args.dry_run: print(f"Dry run: segment={args.segment}; no FYERS or Google Sheets request will be made."); return 0
 try:
  config=RuntimeConfig.from_environ(os.environ); http=requests.Session(); catalog=FyersInstrumentCatalog.download(http); gateway=GoogleSheetGateway.from_service_account_json(config.google_service_account_json,config.sheet_id)
  automated=AutomatedFyersTokenProvider(config,http,lambda:int(time.time())); fallback=FyersTokenProvider(config,http) if config.fyers_refresh_token else None
  worker=LiveChainWorker(catalog,FallbackTokenProvider(automated,fallback),lambda token:FyersDataFeed(f"{config.fyers_client_id}:{token}"),LatestMarketCache(),gateway,SystemClock(),config.flush_seconds)
  return worker.run(SessionSegment.parse(args.segment),max_cycles=1 if args.once else None)
 except ConfigurationError as exc: print(f"Configuration error: {exc}"); return 2
 except InstrumentDiscoveryError as exc: print(f"Worker diagnostic: {exc}"); return 3
 except Exception as exc: print(f"Worker error: {type(exc).__name__}"); return 3
