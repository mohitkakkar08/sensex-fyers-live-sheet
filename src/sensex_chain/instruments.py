"""FYERS BSE derivatives-master parsing and current-expiry selection."""
from __future__ import annotations
import csv, io, re
from dataclasses import dataclass
from functools import cached_property
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, Sequence
INSTRUMENT_MASTER_URL="https://public.fyers.in/sym_details/BSE_FO.csv"
INDEX_SYMBOL="BSE:SENSEX-INDEX"
INDIA_VIX_SYMBOL="NSE:INDIAVIX-INDEX"
class InstrumentDiscoveryError(ValueError): pass
@dataclass(frozen=True)
class OptionContract:
    symbol:str; underlying:str; expiry:date; strike:Decimal; option_type:str
@dataclass(frozen=True)
class CurrentExpiryChain:
    expiry: date
    contracts: tuple[OptionContract, ...]

    @cached_property
    def symbols(self) -> tuple[str, ...]:
        return (INDEX_SYMBOL, INDIA_VIX_SYMBOL) + tuple(contract.symbol for contract in self.contracts)

    @cached_property
    def option_symbols(self) -> frozenset[str]:
        return frozenset(contract.symbol for contract in self.contracts)

    @cached_property
    def strike_pairs(self) -> tuple[tuple[Decimal, OptionContract, OptionContract], ...]:
        by_strike: dict[Decimal, dict[str, OptionContract]] = {}
        for contract in self.contracts:
            by_strike.setdefault(contract.strike, {})[contract.option_type] = contract
        return tuple(
            (strike, contracts["CE"], contracts["PE"])
            for strike, contracts in sorted(by_strike.items())
            if "CE" in contracts and "PE" in contracts
        )
class FyersInstrumentCatalog:
    def __init__(self,contracts:Iterable[OptionContract])->None: self._contracts=tuple(contracts)
    @classmethod
    def from_csv(cls,contents:str)->"FyersInstrumentCatalog":
        rows=list(csv.reader(io.StringIO(contents)))
        if not rows: raise InstrumentDiscoveryError("INSTRUMENT_MASTER_EMPTY")
        contracts=[]; header={_normalize_header(v) for v in rows[0]}
        if "symbolticker" in header or "underlyingsymbol" in header:
            for row in csv.DictReader(io.StringIO(contents)):
                c=_parse_named(row)
                if c: contracts.append(c)
        else:
            for row in rows:
                c=_parse_positional(row)
                if c: contracts.append(c)
        return cls(contracts)
    @classmethod
    def download(cls,http:object)->"FyersInstrumentCatalog":
        try:
            response=http.get(INSTRUMENT_MASTER_URL,timeout=30); response.raise_for_status(); return cls.from_csv(response.text)
        except InstrumentDiscoveryError: raise
        except Exception: raise InstrumentDiscoveryError("INSTRUMENT_MASTER_DOWNLOAD") from None
    def current_sensex_chain(self,today:date)->CurrentExpiryChain:
        candidates=[c for c in self._contracts if c.underlying=="SENSEX" and c.expiry>=today]
        if not candidates: raise InstrumentDiscoveryError("INSTRUMENT_MASTER_NO_SENSEX_OPTIONS")
        for expiry in sorted({c.expiry for c in candidates}):
            contracts=tuple(sorted((c for c in candidates if c.expiry==expiry),key=lambda c:(c.strike,c.option_type,c.symbol)))
            if {"CE","PE"}.issubset({c.option_type for c in contracts}): return CurrentExpiryChain(expiry,contracts)
        raise InstrumentDiscoveryError("INSTRUMENT_MASTER_NO_VALID_EXPIRY")
def chunk_subscriptions(symbols:Sequence[str],max_symbols:int=200)->list[list[str]]:
    if max_symbols<1: raise ValueError("max_symbols must be positive")
    return [list(symbols[i:i+max_symbols]) for i in range(0,len(symbols),max_symbols)]
def _parse_positional(row:list[str])->OptionContract|None:
    if len(row)<14 or row[13].strip().upper()!="SENSEX": return None
    match=re.search(r"\s(\d+(?:\.\d+)?)\s+(CE|PE)\s*$",row[1].strip(),re.I)
    if not match: return None
    try: return OptionContract(row[9].strip(),"SENSEX",datetime.fromtimestamp(int(float(row[8])),tz=timezone.utc).date(),Decimal(match.group(1)),match.group(2).upper())
    except (ValueError,InvalidOperation,IndexError): return None
def _parse_named(row:dict[str,str|None])->OptionContract|None:
    normalized={_normalize_header(k):(v or "").strip() for k,v in row.items() if k}
    symbol=_value(normalized,"symbolticker","symbol"); underlying=_value(normalized,"underlyingsymbol","underlying").upper(); opt=_value(normalized,"optiontype").upper()
    if not symbol or underlying!="SENSEX" or opt not in {"CE","PE"}: return None
    try: return OptionContract(symbol,underlying,_parse_date(_value(normalized,"expirydate","expiry")),Decimal(_value(normalized,"strikeprice","strike").replace(",","")),opt)
    except (ValueError,InvalidOperation): return None
def _normalize_header(value:str)->str: return "".join(c for c in value.lower() if c.isalnum())
def _value(row:dict[str,str],*keys:str)->str:
    for k in keys:
        if row.get(k): return row[k]
    return ""
def _parse_date(value:str)->date:
    for p in ("%Y-%m-%d","%d-%b-%Y","%d-%m-%Y"):
        try:return datetime.strptime(value,p).date()
        except ValueError:pass
    raise ValueError
