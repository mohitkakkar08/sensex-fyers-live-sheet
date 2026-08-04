"""Supervisor that streams one SENSEX expiry until its market-time boundary."""
from __future__ import annotations
from collections.abc import Callable
from typing import Protocol
from .cache import LatestMarketCache
from .instruments import CurrentExpiryChain, FyersInstrumentCatalog
from .sheet import WorkerStatus
from .timebox import SessionSegment, seconds_remaining
class Clock(Protocol):
 def now(self): ...
 def sleep(self,seconds:float)->None: ...
class TokenProvider(Protocol):
 def access_token(self)->str: ...
class DataFeed(Protocol):
 def start(self,symbols,on_tick)->None: ...
 def stop(self)->None: ...
class SheetGateway(Protocol):
 def write_snapshot(self,snapshot,status:WorkerStatus)->None: ...
class LiveChainWorker:
 def __init__(self,catalog:FyersInstrumentCatalog,token_provider:TokenProvider,feed_factory:Callable[[str],DataFeed],cache:LatestMarketCache,gateway:SheetGateway,clock:Clock,flush_seconds:int)->None:
  self._catalog=catalog; self._token_provider=token_provider; self._feed_factory=feed_factory; self._cache=cache; self._gateway=gateway; self._clock=clock; self._flush_seconds=flush_seconds
 def run(self,segment:SessionSegment,max_cycles:int|None=None)->int:
  now=self._clock.now()
  if seconds_remaining(now,segment)<=0:return 0
  chain:CurrentExpiryChain=self._catalog.current_sensex_chain(now.date()); token=self._token_provider.access_token(); feeds:list[DataFeed]=[]
  try:
   feed=self._feed_factory(token); feed.start(chain.symbols,self._cache.upsert); feeds.append(feed); cycles=0
   while seconds_remaining(self._clock.now(),segment)>0:
    current=self._clock.now(); self._gateway.write_snapshot(self._cache.snapshot(chain,current),self._status(chain,current,feeds)); cycles+=1
    if max_cycles is not None and cycles>=max_cycles:break
    self._clock.sleep(min(self._flush_seconds,seconds_remaining(current,segment)))
   return 0
  finally:
   for feed in feeds:feed.stop()
 def _status(self,chain:CurrentExpiryChain,now,feeds:list[DataFeed])->WorkerStatus:
  coverage=self._cache.coverage(chain)
  if coverage.tick_count==0:
   socket_error=next((getattr(feed,'diagnostic_code') for feed in feeds if getattr(feed,'diagnostic_code','') in {'SOCKET_RUNTIME_ERROR','SOCKET_START_FAILED'}),None)
   return WorkerStatus.waiting_for_ticks(now,socket_error or 'SOCKET_SUBSCRIBED_NO_TICKS')
  if not coverage.has_underlying_tick or coverage.option_tick_count==0:return WorkerStatus.partial_live(now,coverage.tick_count,coverage.option_tick_count)
  return WorkerStatus.live(now,coverage.tick_count,coverage.option_tick_count)
