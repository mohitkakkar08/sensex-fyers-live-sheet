"""Google Sheets output gateway for SENSEX chain snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .cache import ChainSnapshot, MarketTick


SHEET_NAME = "SENSEX"
WIDTH = 38  # A:AL, matching the provided CE / Strike / PE option-chain layout.
SUMMARY_HEADERS = ["Instrument", "Prev Close", "Open", "High", "Low", "LTP", "LTP Change", "LTP Change %"]
CHAIN_HEADERS = [
    "CE Prev Close", "CE Low", "CE High", "CE Open", "CE Rho", "CE Theta", "CE Vega", "CE Gamma",
    "CE Delta", "CE IV", "CE OI", "CE OI Change", "CE OI Change %", "CE Volume", "CE LTP Change",
    "CE LTP Change %", "CE LTP", "Strike", "PE LTP", "PE LTP Change", "PE LTP Change %", "PE Volume",
    "PE OI Change", "PE OI", "PE OI Change %", "PE IV", "PE Delta", "PE Gamma", "PE Vega", "PE Theta",
    "PE Rho", "PE Open", "PE High", "PE Low", "PE Prev Close", "Last Updated At", "CE VWAP", "PE VWAP",
]


class SheetGatewayError(RuntimeError):
    """Raised with a safe diagnostic code when Google Sheets output fails."""


@dataclass(frozen=True)
class WorkerStatus:
    state: str
    updated_at: datetime
    diagnostic_code: str = "OK"
    tick_count: int = 0
    option_tick_count: int = 0

    @classmethod
    def connected(cls, updated_at: datetime) -> "WorkerStatus":
        return cls("LIVE", updated_at)

    @classmethod
    def waiting_for_ticks(cls, updated_at: datetime, diagnostic_code: str = "SOCKET_SUBSCRIBED_NO_TICKS") -> "WorkerStatus":
        return cls("WAITING_FOR_TICKS", updated_at, diagnostic_code)
    @classmethod
    def partial_live(cls, updated_at: datetime, tick_count: int, option_tick_count: int) -> "WorkerStatus":
        return cls("PARTIAL_LIVE", updated_at, "MARKET_DATA_PARTIAL", tick_count, option_tick_count)

    @classmethod
    def live(cls, updated_at: datetime, tick_count: int, option_tick_count: int) -> "WorkerStatus":
        return cls("LIVE", updated_at, "OK", tick_count, option_tick_count)


class GoogleSheetGateway:
    """Writes a complete snapshot in one Google Sheets values batch request."""

    def __init__(self, sheets_service: Any, sheet_id: str) -> None:
        self._sheets = sheets_service
        self._sheet_id = sheet_id
        self._layout_ready = False

    @classmethod
    def from_service_account_json(cls, service_account_json: str, sheet_id: str) -> "GoogleSheetGateway":
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_info(
                json.loads(service_account_json),
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            return cls(build("sheets", "v4", credentials=credentials, cache_discovery=False), sheet_id)
        except Exception as exc:
            raise SheetGatewayError("SHEET_AUTHORIZATION_FAILED") from exc

    def ensure_layout(self) -> None:
        """Headers are rewritten with every snapshot so the layout is idempotent."""

        self._layout_ready = True

    def write_snapshot(self, snapshot: ChainSnapshot, status: WorkerStatus) -> None:
        self.ensure_layout()
        data = [
            {"range": f"{SHEET_NAME}!A1:AL3", "values": _summary_values(snapshot, status)},
            {"range": f"{SHEET_NAME}!A6:AL{6 + len(snapshot.rows)}", "values": _chain_values(snapshot)},
        ]
        try:
            self._sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=self._sheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": data},
            ).execute()
        except Exception as exc:
            raise SheetGatewayError("SHEET_WRITE_FAILED") from exc


def _summary_values(snapshot: ChainSnapshot, status: WorkerStatus) -> list[list[object]]:
    index = snapshot.underlying
    row1 = _pad(SUMMARY_HEADERS)
    row2 = _pad([
        index.symbol, _cell(index.prev_close), _cell(index.open), _cell(index.high), _cell(index.low), _cell(index.ltp),
        _change(index), _change_percent(index),
    ])
    row3 = _pad([
        "Status", status.state, "Diagnostic", status.diagnostic_code, "Ticks", status.tick_count,
        "Option Ticks", status.option_tick_count, "Expiry", snapshot.expiry.isoformat(), "Updated", status.updated_at.isoformat(),
    ])
    return [row1, row2, row3]


def _chain_values(snapshot: ChainSnapshot) -> list[list[object]]:
    values = [list(CHAIN_HEADERS)]
    for row in snapshot.rows:
        call, put = row.call, row.put
        values.append([
            _cell(call.prev_close), _cell(call.low), _cell(call.high), _cell(call.open), "", "", "", "", "", "",
            _cell(call.oi), _cell(call.oi_change), _oi_change_percent(call), _cell(call.volume), _change(call),
            _change_percent(call), _cell(call.ltp), float(row.strike), _cell(put.ltp), _change(put), _change_percent(put),
            _cell(put.volume), _cell(put.oi_change), _cell(put.oi), _oi_change_percent(put), "", "", "", "", "", "",
            _cell(put.open), _cell(put.high), _cell(put.low), _cell(put.prev_close), snapshot.updated_at.isoformat(),
            _cell(call.vwap), _cell(put.vwap),
        ])
    return values


def _pad(values: list[object]) -> list[object]:
    return values + [""] * (WIDTH - len(values))


def _cell(value: float | None) -> float | str:
    return "" if value is None else value


def _change(tick: MarketTick) -> float | str:
    if tick.ltp is None or tick.prev_close is None:
        return ""
    return tick.ltp - tick.prev_close


def _change_percent(tick: MarketTick) -> float | str:
    if tick.ltp is None or tick.prev_close in (None, 0):
        return ""
    return round(((tick.ltp - tick.prev_close) / tick.prev_close) * 100, 4)


def _oi_change_percent(tick: MarketTick) -> float | str:
    if tick.oi is None or tick.oi_change is None:
        return ""
    previous_oi = tick.oi - tick.oi_change
    if previous_oi == 0:
        return ""
    return round((tick.oi_change / previous_oi) * 100, 4)
