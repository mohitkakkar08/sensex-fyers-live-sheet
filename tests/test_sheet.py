from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sensex_chain.cache import ChainRow, ChainSnapshot, MarketTick
from sensex_chain.sheet import GoogleSheetGateway, WorkerStatus
from sensex_chain.timebox import KOLKATA


class FakeRequest:
    def __init__(self, callback) -> None:
        self._callback = callback

    def execute(self) -> None:
        self._callback()


class FakeValues:
    def __init__(self, parent) -> None:
        self.parent = parent

    def batchUpdate(self, *, spreadsheetId: str, body: dict[str, object]) -> FakeRequest:
        def save() -> None:
            self.parent.values_batch_updates += 1
            self.parent.last_sheet_id = spreadsheetId
            self.parent.last_body = body

        return FakeRequest(save)


class FakeSpreadsheets:
    def __init__(self, parent) -> None:
        self.parent = parent

    def values(self) -> FakeValues:
        return FakeValues(self.parent)


class FakeSheetsService:
    def __init__(self) -> None:
        self.values_batch_updates = 0
        self.last_sheet_id = ""
        self.last_body: dict[str, object] = {}

    def spreadsheets(self) -> FakeSpreadsheets:
        return FakeSpreadsheets(self)


def snapshot() -> ChainSnapshot:
    now = datetime(2026, 8, 4, 9, 15, tzinfo=KOLKATA)
    return ChainSnapshot(
        expiry=date(2026, 8, 6),
        updated_at=now,
        underlying=MarketTick("BSE:SENSEX-INDEX", ltp=80050.0, prev_close=80000.0),
        rows=(
            ChainRow(
                strike=Decimal("80000"),
                call=MarketTick("BSE:SENSEX26AUG80000CE", ltp=125.0, oi=400.0),
                put=MarketTick("BSE:SENSEX26AUG80000PE"),
            ),
        ),
    )


def test_write_snapshot_uses_one_values_batch_update() -> None:
    service = FakeSheetsService()
    gateway = GoogleSheetGateway(service, "sheet-id")

    gateway.write_snapshot(snapshot(), WorkerStatus.connected(snapshot().updated_at))

    assert service.values_batch_updates == 1
    assert service.last_sheet_id == "sheet-id"
    assert [item["range"] for item in service.last_body["data"]] == ["SENSEX!A1:AT3", "SENSEX!A6:AT7"]


def test_missing_market_fields_are_written_as_blank_cells() -> None:
    service = FakeSheetsService()
    gateway = GoogleSheetGateway(service, "sheet-id")

    gateway.write_snapshot(snapshot(), WorkerStatus.connected(snapshot().updated_at))

    chain_rows = service.last_body["data"][1]["values"]
    assert "" in chain_rows[1]
