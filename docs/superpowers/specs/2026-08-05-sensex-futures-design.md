# SENSEX Futures Feed Design

## Goal

Add the nearest unexpired BSE SENSEX futures contract to the existing FYERS live worker and display its live fields in columns `L:Z` of the `SENSEX` tab.

## Design

The FYERS BSE derivatives master is already downloaded once at worker start. Its positional rows include SENSEX futures such as `BSE:SENSEX26AUGFUT`, with expiry epoch at index 8 and ticker at index 9. The catalog will retain valid SENSEX futures, select the nearest contract whose expiry is today or later, and attach it to the current option-expiry selection.

The selected future is appended to the existing one-socket subscription list. Its tick uses the existing cache and `MarketTick` model, so it inherits the current merge semantics for OHLC, LTP, volume, OI, OI change, and VWAP. No second socket, REST polling path, or new secret is introduced.

The Sheets gateway writes a `L:Z` future summary block: instrument, previous close, open, high, low, LTP, LTP change, LTP change %, volume, OI, OI change, OI change %, and VWAP. The two existing visual separator columns are retained to align the requested sample layout. A missing future contract or tick is represented by blank cells, never invented data.

## Validation

Tests will prove futures parsing/nearest-expiry selection, subscription inclusion, cache snapshot presence, and exact `L:Z` output values. The full pytest suite, Python compilation, dry-run command, and whitespace diff check must pass before publication.
