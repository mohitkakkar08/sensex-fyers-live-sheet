"""Google Sheets output gateway for SENSEX chain snapshots."""
from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from .cache import ChainSnapshot, MarketTick
from .timebox import KOLKATA
SHEET_NAME="SENSEX"; WIDTH=38
SUMMARY_HEADERS=["Instrument","Prev Close","Open","High","Low","LTP","LTP Change","LTP Change %"]
CHAIN_HEADERS=["CE Prev Close","CE Low","CE High","CE Open","CE Rho","CE Theta","CE Vega","CE Gamma","CE Delta","CE IV","CE OI","CE OI Change","CE OI Change %","CE Volume","CE LTP Change","CE LTP Change %","CE LTP","Strike","PE LTP","PE LTP Change","PE LTP Change %","PE Volume","PE OI Change","PE OI","PE OI Change %","PE IV","PE Delta","PE Gamma","PE Vega","PE Theta","PE Rho","PE Open","PE High","PE Low","PE Prev Close","Last Updated At","CE VWAP","PE VWAP"]
class SheetGatewayError(RuntimeError): pass
@dataclass(frozen=True)
class WorkerStatus:
 state:str; updated_at:datetime; diagnostic_code:str="OK"; tick_count:int=0; option_tick_count:int=0
 @classmethod
 def connected(cls,updated_at:datetime)->"WorkerStatus":return cls("LIVE",updated_at)
 @classmethod
 def waiting_for_ticks(cls,updated_at:datetime,diagnostic_code:str="SOCKET_SUBSCRIBED_NO_TICKS")->"WorkerStatus":return cls("WAITING_FOR_TICKS",updated_at,diagnostic_code)
 @classmethod
 def partial_live(cls,updated_at:datetime,tick_count:int,option_tick_count:int)->"WorkerStatus":return cls("PARTIAL_LIVE",updated_at,"MARKET_DATA_PARTIAL",tick_count,option_tick_count)
 @classmethod
 def live(cls,updated_at:datetime,tick_count:int,option_tick_count:int)->"WorkerStatus":return cls("LIVE",updated_at,"OK",tick_count,option_tick_count)
class GoogleSheetGateway:
 def __init__(self,sheets_service:Any,sheet_id:str)->None:self._sheets=sheets_service;self._sheet_id=sheet_id;self._layout_ready=False
 @classmethod
 def from_service_account_json(cls,service_account_json:str,sheet_id:str)->"GoogleSheetGateway":
  try:
   from google.oauth2 import service_account
   from googleapiclient.discovery import build
   credentials=service_account.Credentials.from_service_account_info(json.loads(service_account_json),scopes=["https://www.googleapis.com/auth/spreadsheets"])
   return cls(build("sheets","v4",credentials=credentials,cache_discovery=False),sheet_id)
  except Exception as exc:raise SheetGatewayError("SHEET_AUTHORIZATION_FAILED") from exc
 def ensure_layout(self)->None:self._layout_ready=True
 def write_snapshot(self,snapshot:ChainSnapshot,status:WorkerStatus)->None:
  self.ensure_layout(); data=[{"range":f"{SHEET_NAME}!A1:AL4","values":_summary_values(snapshot,status)},{"range":f"{SHEET_NAME}!A6:AL{6+len(snapshot.rows)}","values":_chain_values(snapshot)}]
  try:self._sheets.spreadsheets().values().batchUpdate(spreadsheetId=self._sheet_id,body={"valueInputOption":"USER_ENTERED","data":data}).execute()
  except Exception as exc:raise SheetGatewayError("SHEET_WRITE_FAILED") from exc
def _summary_values(snapshot:ChainSnapshot,status:WorkerStatus)->list[list[object]]:
 i=snapshot.underlying; v=snapshot.india_vix
 return [_pad(SUMMARY_HEADERS),_pad([i.symbol,_cell(i.prev_close),_cell(i.open),_cell(i.high),_cell(i.low),_cell(i.ltp),_change(i),_change_percent(i)]),_pad([v.symbol,_cell(v.prev_close),_cell(v.open),_cell(v.high),_cell(v.low),_cell(v.ltp),_change(v),_change_percent(v)]),_pad(["Status",status.state,"Diagnostic",status.diagnostic_code,"Ticks",status.tick_count,"Option Ticks",status.option_tick_count,"Expiry",snapshot.expiry.isoformat(),"Updated",_timestamp(status.updated_at)])]
def _chain_values(snapshot:ChainSnapshot)->list[list[object]]:
 values=[list(CHAIN_HEADERS)]
 for row in snapshot.rows:
  c,p=row.call,row.put
  values.append([_cell(c.prev_close),_cell(c.low),_cell(c.high),_cell(c.open),_cell(c.rho),_cell(c.theta),_cell(c.vega),_cell(c.gamma),_cell(c.delta),_cell(c.iv),_cell(c.oi),_cell(c.oi_change),_oi_change_percent(c),_cell(c.volume),_change(c),_change_percent(c),_cell(c.ltp),float(row.strike),_cell(p.ltp),_change(p),_change_percent(p),_cell(p.volume),_cell(p.oi_change),_cell(p.oi),_oi_change_percent(p),_cell(p.iv),_cell(p.delta),_cell(p.gamma),_cell(p.vega),_cell(p.theta),_cell(p.rho),_cell(p.open),_cell(p.high),_cell(p.low),_cell(p.prev_close),_timestamp(snapshot.updated_at),_cell(c.vwap),_cell(p.vwap)])
 return values
def _pad(values:list[object])->list[object]:return values+[""]*(WIDTH-len(values))
def _cell(value:float|None)->float|str:return "" if value is None else value
def _change(t:MarketTick)->float|str:return "" if t.ltp is None or t.prev_close is None else t.ltp-t.prev_close
def _change_percent(t:MarketTick)->float|str:return "" if t.ltp is None or t.prev_close in (None,0) else round(((t.ltp-t.prev_close)/t.prev_close)*100,4)
def _oi_change_percent(t:MarketTick)->float|str:
 if t.oi is None or t.oi_change is None:return ""
 prior=t.oi-t.oi_change
 return "" if prior==0 else round((t.oi_change/prior)*100,4)

def _timestamp(value: datetime) -> str:
 return value.astimezone(KOLKATA).strftime('%d/%m/%Y %H:%M:%S IST')
