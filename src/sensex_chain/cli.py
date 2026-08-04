"""Command-line entry point for a scheduled data-only worker."""
from __future__ import annotations
import argparse, os, time
from collections.abc import Mapping
from datetime import datetime
import requests
from .auth import AuthenticationError, AutomatedFyersTokenProvider, FallbackTokenProvider, FyersTokenProvider
from .cache import LatestMarketCache
from .config import ConfigurationError, RuntimeConfig
from .instruments import FyersInstrumentCatalog, InstrumentDiscoveryError
from .sheet import GoogleSheetGateway, SheetGatewayError
from .socket import DataFeedError, FyersDataFeed
from .option_chain import FyersOptionChainEnricher
from .timebox import KOLKATA, SessionSegment
from .worker import LiveChainWorker
class SystemClock:
 def now(self)->datetime:return datetime.now(KOLKATA)
 def sleep(self,seconds:float)->None:time.sleep(seconds)
class DebugMarketCache(LatestMarketCache):
 """Prints a strictly bounded sample of market ticks for manual diagnostics."""
 def __init__(self)->None:super().__init__();self._debug_count=0
 def upsert(self,raw_tick:Mapping[str,object])->None:
  super().upsert(raw_tick)
  if self._debug_count<5:
   symbol=str(raw_tick.get('symbol') or raw_tick.get('symbol_name') or 'UNKNOWN')
   ltp=raw_tick.get('ltp') or raw_tick.get('lp') or ''
   print(f'Diagnostic: WEBSOCKET_TICK; number={self._debug_count+1}; symbol={symbol}; ltp={ltp}; fields={",".join(sorted(map(str,raw_tick.keys())))}')
   self._debug_count+=1
def build_parser()->argparse.ArgumentParser:
 p=argparse.ArgumentParser(description='Stream current-expiry SENSEX options to Google Sheets')
 p.add_argument('--segment',required=True,choices=['morning','afternoon']);p.add_argument('--dry-run',action='store_true');p.add_argument('--once',action='store_true');p.add_argument('--debug-ticks',action='store_true',help='Print the first five websocket ticks for a manual diagnostic run')
 return p
def main(argv:list[str]|None=None)->int:
 args=build_parser().parse_args(argv)
 if args.dry_run:print(f'Diagnostic: DRY_RUN; segment={args.segment}; no FYERS or Google Sheets request will be made.');return 0
 try:
  config=RuntimeConfig.from_environ(os.environ);print('Diagnostic: CONFIGURATION_READY');http=requests.Session();catalog=FyersInstrumentCatalog.download(http);print('Diagnostic: INSTRUMENT_CATALOG_READY');gateway=GoogleSheetGateway.from_service_account_json(config.google_service_account_json,config.sheet_id);print('Diagnostic: GOOGLE_SHEETS_GATEWAY_READY')
  automated=AutomatedFyersTokenProvider(config,http,lambda:int(time.time()));fallback=FyersTokenProvider(config,http) if config.fyers_refresh_token else None; cache=DebugMarketCache() if args.debug_ticks else LatestMarketCache()
  worker=LiveChainWorker(catalog,FallbackTokenProvider(automated,fallback),lambda token:FyersDataFeed(f'{config.fyers_client_id}:{token}'),cache,gateway,SystemClock(),config.flush_seconds,option_chain_factory=lambda token:FyersOptionChainEnricher(config.fyers_client_id,token))
  print('Diagnostic: FYERS_AUTHENTICATION_STARTING');result=worker.run(SessionSegment.parse(args.segment),max_cycles=1 if args.once else None);print('Diagnostic: WORKER_STOPPED_CLEANLY');return result
 except ConfigurationError as exc:print(f'Diagnostic: CONFIGURATION_ERROR; {exc}');return 2
 except (AuthenticationError,InstrumentDiscoveryError,DataFeedError,SheetGatewayError) as exc:print(f'Diagnostic: {exc}');return 3
 except Exception as exc:print(f'Diagnostic: UNEXPECTED_{type(exc).__name__.upper()}');return 3
