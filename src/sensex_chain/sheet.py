"""Google Sheets output gateway for SENSEX chain snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .cache import ChainSnapshot, MarketTick


SHEET_NAME = "SENSEX"
WIDTH = 46  # A:AT
SUMMARY_HEADERS = ["Instrument", "Prev Close", "Open", "High", "Low", "LTP", "LTP Change", "LTP Change %"]
CHAIN_HEADERS = [
    "CE Prev Close", "CE Low", "CE High", "CE Open", "CE OI", "CE OI Change", "CE Volume", "CE LTP",
    "CE LTP Change %", "CE VWAP", "CE Instrument", "Strike", "PE Instrument", "PE LTP", "PE Volume",
    "PE OI Change", "PE OI", "PE VWAP", "PE LTP Change %", "PE Open", "PE High", "PE Low", "PE Prev Close",
    "Expiry Date", "Last Updated At", "Call INTRINSIC", "Call EXTRINSIC", "Put INTRINSIC", "Put EXTRINSIC",
]


@dataclass(frozen=True)
class WorkerStatus:
    state: str
    updated_at: datetime

    @classmethod
    def connected(cls, updated_at: datetime) -> "WorkerStatus":
        return cls("CONNECTED", updated_at)


class GoogleSheetGateway:
    """Writes a complete snapshot in one Google Sheets values batch request."""

    def __init__(self, sheets_service: Any, sheet_id: str) -> None:
        self._sheets = sheets_service
        self._sheet_id = sheet_id
        self._layout_ready = False

    @classmethod
    def from_service_account_json(cls, service_account_json: str, sheet_id: str) -> "GoogleSheetGateway":
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_info(
            json.loads(service_account_json),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        return cls(build("sheets", "v4", credentials=credentials, cache_discovery=False), sheet_id)

    def ensure_layout(self) -> None:
        """The headers are included in each snapshot, making this operation idempotent."""

        self._layout_ready = True

    def write_snapshot(self, snapshot: ChainSnapshot, status: WorkerStatus) -> None:
        self.ensure_layout()
        data = [
            {"range": f"{SHEET_NAME}!A1:AT3", "values": _summary_values(snapshot, status)},
            {"range": f"{SHEET_NAME}!A6:AT{6 + len(snapshot.rows)}", "values": _chain_values(snapshot)},
        ]
        self._sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=self._sheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": data},
        ).execute()


def _summary_values(snapshot: ChainSnapshot, status: WorkerStatus) -> list[list[object]]:
    index = snapshot.underlying
    row1 = _pad(SUMMARY_HEADERS)
    row2 = _pad([
        index.symbol, _cell(index.prev_close), _cell(index.open), _cell(index.high), _cell(index.low), _cell(index.ltp),
        _change(index), _change_percent(index),
    ])
    row3 = _pad(["Status", status.state, "Expiry", snapshot.expiry.isoformat(), "Updated", status.updated_at.isoformat()])
    return [row1, row2, row3]


def _chain_values(snapshot: ChainSnapshot) -> list[list[object]]:
    values = [_pad(CHAIN_HEADERS)]
    for offset, row in enumerate(snapshot.rows, start=7):
        call, put = row.call, row.put
        strike = float(row.strike)
        values.append(_pad([
            _cell(call.prev_close), _cell(call.low), _cell(call.high), _cell(call.open), _cell(call.oi), _cell(call.oi_change),
            _cell(call.volume), _cell(call.ltp), _change_percent(call), _cell(call.vwap), call.symbol, strike,
            put.symbol, _cell(put.ltp), _cell(put.volume), _cell(put.oi_change), _cell(put.oi), _cell(put.vwap),
            _change_percent(put), _cell(put.open), _cell(put.high), _cell(put.low), _cell(put.prev_close),
            snapshot.expiry.isoformat(), snapshot.updated_at.isoformat(),
            f"=MAX($F$2-L{offset},0)", f"=IF(H{offset}=\"\",\"\",H{offset}-Z{offset})",
            f"=MAX(L{offset}-$F$2,0)", f"=IF(N{offset}=\"\",\"\",N{offset}-AB{offset})",
        ]))
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
