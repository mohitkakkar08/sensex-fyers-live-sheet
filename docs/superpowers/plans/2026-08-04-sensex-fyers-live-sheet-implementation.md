# SENSEX FYERS Live Sheet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a data-only Python worker that streams FYERS BSE SENSEX current-expiry options into the configured Google Sheet every 10 seconds, plus two public-repository GitHub Actions schedules.

**Architecture:** A small Python package separates configuration, instrument discovery, token refresh, the FYERS socket adapter, the market-data cache, and the Google Sheets gateway. Each scheduled job resolves the current expiry, starts one or more read-only data sockets, and flushes a complete rectangular snapshot to Sheets on a 10-second cadence until its segment end time.

**Tech Stack:** Python 3.12, `fyers-apiv3==3.1.14`, `requests`, `google-api-python-client`, `google-auth`, `pytest`, GitHub Actions Ubuntu runners.

## Global Constraints

- The worker is market-data-only: it must not import or call FYERS order, position, funds, holdings, or trade APIs.
- Repository source, workflow YAML, logs, test fixtures, and Sheets cells must never contain a secret.
- Runtime secrets are `FYERS_CLIENT_ID`, `FYERS_SECRET_KEY`, `FYERS_REFRESH_TOKEN`, `FYERS_PIN`, `GOOGLE_SERVICE_ACCOUNT_JSON`, and `GOOGLE_SHEET_ID`.
- Current expiry is selected from the FYERS BSE derivatives instrument master, never from a hard-coded weekday.
- Every Google Sheets update is a batch request; the normal cadence is one completed snapshot every 10 seconds.
- A FYERS field that is not supplied is written as blank, not calculated or guessed.
- The worker uses Asia/Kolkata time and exits at 12:15 or 15:30 IST even if a GitHub schedule begins late.
- This workspace is not a Git repository; validate files and tests but do not issue git commit commands.

---

## File structure

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Runtime/test dependencies and package/test configuration |
| `src/sensex_chain/config.py` | Secret validation and immutable runtime settings |
| `src/sensex_chain/timebox.py` | IST session limits and cadence calculations |
| `src/sensex_chain/instruments.py` | FYERS BSE_FO CSV download, header normalization, current-expiry selection, subscription chunking |
| `src/sensex_chain/auth.py` | FYERS refresh-token request and redacted failures |
| `src/sensex_chain/socket.py` | Narrow, read-only FYERS DataSocket adapter |
| `src/sensex_chain/cache.py` | Thread-safe latest-tick cache and tick normalization |
| `src/sensex_chain/sheet.py` | Google service-account client, SENSEX-sheet layout, batch writer |
| `src/sensex_chain/worker.py` | Orchestration, reconnect supervision, 10-second flush loop |
| `src/sensex_chain/cli.py` | `python -m` entry point and dry-run command |
| `tests/` | Unit and integration-style tests with fake HTTP/socket/sheet clients |
| `.github/workflows/sensex-live.yml` | Morning/afternoon GitHub Actions runs |
| `.env.example`, `.gitignore`, `README.md` | Safe configuration and operator instructions |

## Task 1: Package skeleton, configuration, and session timing

**Files:**
- Create: `pyproject.toml`
- Create: `src/sensex_chain/__init__.py`
- Create: `src/sensex_chain/config.py`
- Create: `src/sensex_chain/timebox.py`
- Create: `tests/test_config.py`
- Create: `tests/test_timebox.py`

**Interfaces:**
- Produces `RuntimeConfig.from_environ(environ: Mapping[str, str]) -> RuntimeConfig`.
- Produces `SessionSegment.parse(value: str) -> SessionSegment` and `SessionSegment.ends_at(now: datetime) -> datetime`.
- Later tasks use `config.sheet_id`, `config.fyers_client_id`, `config.fyers_secret_key`, `config.fyers_refresh_token`, `config.fyers_pin`, `config.google_service_account_json`, `config.flush_seconds` and `segment.ends_at()`.

- [ ] **Step 1: Write the failing configuration tests**

```python
def test_from_environ_requires_all_six_runtime_secrets():
    with pytest.raises(ConfigurationError, match="FYERS_PIN"):
        RuntimeConfig.from_environ({"FYERS_CLIENT_ID": "id"})

def test_from_environ_never_echoes_secret_values():
    config = RuntimeConfig.from_environ(valid_environ())
    assert "super-secret" not in repr(config)
    assert config.flush_seconds == 10
```

- [ ] **Step 2: Run the configuration tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`

Expected: FAIL because `sensex_chain.config` does not exist.

- [ ] **Step 3: Implement immutable settings with redacted representation**

```python
@dataclass(frozen=True, repr=False)
class RuntimeConfig:
    fyers_client_id: str
    fyers_secret_key: str
    fyers_refresh_token: str
    fyers_pin: str
    google_service_account_json: str
    sheet_id: str
    flush_seconds: int = 10

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> "RuntimeConfig":
        required = ("FYERS_CLIENT_ID", "FYERS_SECRET_KEY", "FYERS_REFRESH_TOKEN",
                    "FYERS_PIN", "GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_SHEET_ID")
        missing = [name for name in required if not environ.get(name, "").strip()]
        if missing:
            raise ConfigurationError("Missing required environment variable(s): " + ", ".join(missing))
        return cls(*(environ[name] for name in required))
```

- [ ] **Step 4: Add timing tests and implement the two explicit segments**

```python
def test_afternoon_segment_ends_at_1530_india_time():
    now = datetime(2026, 8, 4, 12, 20, tzinfo=KOLKATA)
    assert SessionSegment.AFTERNOON.ends_at(now) == datetime(2026, 8, 4, 15, 30, tzinfo=KOLKATA)

def test_wait_seconds_is_zero_after_segment_end():
    after_close = datetime(2026, 8, 4, 15, 31, tzinfo=KOLKATA)
    assert seconds_remaining(after_close, SessionSegment.AFTERNOON) == 0
```

Implement `SessionSegment.MORNING = (09:15, 12:15)` and `SessionSegment.AFTERNOON = (12:15, 15:30)` using `ZoneInfo("Asia/Kolkata")`; reject any other segment string.

- [ ] **Step 5: Run the task tests**

Run: `python -m pytest tests/test_config.py tests/test_timebox.py -v`

Expected: PASS.

## Task 2: Current-expiry SENSEX discovery and subscription chunking

**Files:**
- Create: `src/sensex_chain/instruments.py`
- Create: `tests/fixtures/bse_fo_sample.csv`
- Create: `tests/test_instruments.py`

**Interfaces:**
- Consumes `requests.Session` and UTC/IST `date`.
- Produces `OptionContract(symbol: str, expiry: date, strike: Decimal, option_type: Literal["CE", "PE"])`.
- Produces `CurrentExpiryChain(expiry: date, calls: tuple[OptionContract, ...], puts: tuple[OptionContract, ...])`.
- Produces `chunk_subscriptions(symbols: Sequence[str], max_symbols: int = 200) -> list[list[str]]`.
- Later tasks call `FyersInstrumentCatalog.current_sensex_chain(today)` and receive no chain rather than an unsafe guessed expiry.

- [ ] **Step 1: Write failing expiry-selection tests from a compact CSV fixture**

```python
def test_selects_nearest_expiry_with_both_call_and_put():
    chain = catalog.current_sensex_chain(date(2026, 8, 4))
    assert chain.expiry == date(2026, 8, 6)
    assert {contract.option_type for contract in chain.contracts} == {"CE", "PE"}

def test_holiday_shift_uses_next_master_expiry_not_calendar_thursday():
    chain = catalog.current_sensex_chain(date(2026, 8, 12))
    assert chain.expiry == date(2026, 8, 13)

def test_chunks_401_symbols_into_200_200_1():
    assert [len(chunk) for chunk in chunk_subscriptions([f"BSE:X{i}" for i in range(401)])] == [200, 200, 1]
```

- [ ] **Step 2: Run the discovery tests to verify they fail**

Run: `python -m pytest tests/test_instruments.py -v`

Expected: FAIL because `sensex_chain.instruments` does not exist.

- [ ] **Step 3: Implement CSV schema normalization and conservative selection**

```python
INSTRUMENT_MASTER_URL = "https://public.fyers.in/sym_details/BSE_FO.csv"

def current_sensex_chain(self, today: date) -> CurrentExpiryChain:
    candidates = [c for c in self.contracts if c.underlying == "SENSEX" and c.expiry >= today]
    for expiry in sorted({c.expiry for c in candidates}):
        contracts = tuple(c for c in candidates if c.expiry == expiry)
        if any(c.option_type == "CE" for c in contracts) and any(c.option_type == "PE" for c in contracts):
            return CurrentExpiryChain.from_contracts(expiry, contracts)
    raise InstrumentDiscoveryError("No current or future BSE SENSEX CE/PE expiry was found in BSE_FO.csv")
```

Support documented header aliases (`symbol`/`Symbol Ticker`, `expiry`/`Expiry Date`, `strike`/`Strike Price`, `option_type`/`Option Type`, `underlying`/`Underlying Symbol`) and reject rows with unparseable expiry, strike, or option type.

- [ ] **Step 4: Run the discovery test suite**

Run: `python -m pytest tests/test_instruments.py -v`

Expected: PASS.

## Task 3: FYERS refresh-token provider and read-only DataSocket adapter

**Files:**
- Create: `src/sensex_chain/auth.py`
- Create: `src/sensex_chain/socket.py`
- Create: `tests/test_auth.py`
- Create: `tests/test_socket.py`

**Interfaces:**
- Consumes `RuntimeConfig` and a `requests.Session`.
- Produces `FyersTokenProvider.access_token() -> str`.
- Produces `FyersDataFeed.start(symbols: Sequence[str], on_tick: Callable[[Mapping[str, object]], None]) -> None`, `stop() -> None`.
- Later tasks receive normal Python mappings only; they do not depend on FYERS SDK callback classes.

- [ ] **Step 1: Write a failing refresh request test**

```python
def test_refresh_uses_documented_endpoint_and_hash_without_logging_secrets(requests_mock):
    requests_mock.post(REFRESH_URL, json={"s": "ok", "access_token": "token-value"})
    assert provider.access_token() == "token-value"
    request = requests_mock.request_history[0]
    assert request.json()["grant_type"] == "refresh_token"
    assert request.json()["appIdHash"] == hashlib.sha256(b"app:secret").hexdigest()
    assert "secret" not in caplog.text and "1234" not in caplog.text
```

- [ ] **Step 2: Run the auth test to verify it fails**

Run: `python -m pytest tests/test_auth.py -v`

Expected: FAIL because `sensex_chain.auth` does not exist.

- [ ] **Step 3: Implement token renewal with a narrow HTTP client**

```python
REFRESH_URL = "https://api-t1.fyers.in/api/v3/validate-refresh-token"

def access_token(self) -> str:
    app_id_hash = hashlib.sha256(f"{self._config.fyers_client_id}:{self._config.fyers_secret_key}".encode()).hexdigest()
    response = self._http.post(REFRESH_URL, json={
        "grant_type": "refresh_token", "appIdHash": app_id_hash,
        "refresh_token": self._config.fyers_refresh_token, "pin": self._config.fyers_pin,
    }, timeout=20)
    body = response.json()
    if response.status_code != 200 or body.get("s") != "ok" or not body.get("access_token"):
        raise AuthenticationError("FYERS refresh-token exchange failed; replace the expired refresh token if needed")
    return str(body["access_token"])
```

- [ ] **Step 4: Write and run failing/passing socket-adapter tests**

```python
def test_socket_subscribes_only_in_symbol_update_mode(fake_data_socket):
    feed.start(["BSE:SENSEX-INDEX", "BSE:SENSEX26AUG80000CE"], received.append)
    assert fake_data_socket.subscriptions == [(["BSE:SENSEX-INDEX", "BSE:SENSEX26AUG80000CE"], "SymbolUpdate")]
```

Implement the adapter using `fyers_apiv3.FyersWebsocket.data_ws.FyersDataSocket`, pass only the data access token, subscribe with `data_type="SymbolUpdate"`, and expose no trading-session object. Wrap SDK errors in `DataFeedError` without interpolating tokens.

- [ ] **Step 5: Run the Task 3 tests**

Run: `python -m pytest tests/test_auth.py tests/test_socket.py -v`

Expected: PASS.

## Task 4: Tick cache and SENSEX option-chain rows

**Files:**
- Create: `src/sensex_chain/cache.py`
- Create: `tests/test_cache.py`

**Interfaces:**
- Consumes `CurrentExpiryChain`, current index value, and raw DataSocket mappings.
- Produces `LatestMarketCache.upsert(raw_tick: Mapping[str, object]) -> None` and `snapshot(chain: CurrentExpiryChain, now: datetime) -> ChainSnapshot`.
- Produces `ChainRow` with `call`, `strike`, `put`, `expiry`, and `updated_at` fields.
- `sheet.py` uses `ChainSnapshot.rows` and does not inspect raw socket messages.

- [ ] **Step 1: Write failing normalization and blank-field tests**

```python
def test_snapshot_pairs_call_and_put_by_strike_and_preserves_missing_data_as_none():
    cache.upsert({"symbol": "BSE:SENSEX26AUG80000CE", "ltp": 125.0, "oi": 400})
    row = cache.snapshot(chain, now).rows[0]
    assert row.call.ltp == 125.0
    assert row.put.ltp is None

def test_malformed_tick_is_ignored_without_erasing_a_valid_tick():
    cache.upsert(valid_tick)
    cache.upsert({"symbol": "BSE:SENSEX26AUG80000CE", "ltp": "not-a-number"})
    assert cache.snapshot(chain, now).rows[0].call.ltp == valid_tick["ltp"]
```

- [ ] **Step 2: Run the cache tests to verify they fail**

Run: `python -m pytest tests/test_cache.py -v`

Expected: FAIL because `sensex_chain.cache` does not exist.

- [ ] **Step 3: Implement a locked cache with explicit FYERS-to-sheet field aliases**

```python
TICK_ALIASES = {"ltp": ("ltp", "lp"), "open": ("open_price", "open"),
                "high": ("high_price", "high"), "low": ("low_price", "low"),
                "prev_close": ("prev_close_price", "prev_close"),
                "volume": ("vol_traded_today", "volume"), "oi": ("oi", "OI")}

def upsert(self, raw_tick: Mapping[str, object]) -> None:
    symbol = str(raw_tick.get("symbol") or raw_tick.get("symbol_name") or "")
    if not symbol:
        return
    normalized = normalize_tick(raw_tick)
    if normalized is None:
        return
    with self._lock:
        self._ticks[symbol] = normalized
```

Calculate percentage change only when the prior close is nonzero; otherwise write blank. Keep VWAP, OI change, and Greeks blank unless supplied in the tick payload.

- [ ] **Step 4: Run the Task 4 tests**

Run: `python -m pytest tests/test_cache.py -v`

Expected: PASS.

## Task 5: Google Sheets layout and single-batch writer

**Files:**
- Create: `src/sensex_chain/sheet.py`
- Create: `tests/test_sheet.py`

**Interfaces:**
- Consumes `RuntimeConfig.google_service_account_json` and `ChainSnapshot`.
- Produces `GoogleSheetGateway.ensure_layout() -> None`, `write_snapshot(snapshot: ChainSnapshot, status: WorkerStatus) -> None`, and `write_status(status: WorkerStatus) -> None`.
- `worker.py` owns when to call these methods; `sheet.py` owns A1 ranges and Google API payloads.

- [ ] **Step 1: Write failing layout and batch-write tests**

```python
def test_write_snapshot_uses_one_values_batch_update(fake_sheets_service, snapshot):
    gateway.write_snapshot(snapshot, WorkerStatus.connected(snapshot.updated_at))
    assert fake_sheets_service.values_batch_updates == 1
    assert fake_sheets_service.last_ranges == ["SENSEX!A1:AT3", "SENSEX!A6:AT7"]

def test_missing_greeks_are_written_as_blank_cells(fake_sheets_service, snapshot):
    gateway.write_snapshot(snapshot, WorkerStatus.connected(snapshot.updated_at))
    assert "" in fake_sheets_service.last_body["data"][1]["values"][0]
```

- [ ] **Step 2: Run the sheet tests to verify they fail**

Run: `python -m pytest tests/test_sheet.py -v`

Expected: FAIL because `sensex_chain.sheet` does not exist.

- [ ] **Step 3: Implement the `SENSEX` layout and writer**

```python
SUMMARY_HEADERS = ["Instrument", "Prev Close", "Open", "High", "Low", "LTP", "LTP Change", "LTP Change %"]
CHAIN_HEADERS = ["CE Prev Close", "CE Low", "CE High", "CE Open", "CE OI", "CE OI Change", "CE Volume",
                 "CE LTP", "CE Instrument", "Strike", "PE Instrument", "PE LTP", "PE Volume", "PE OI Change",
                 "PE OI", "PE Open", "PE High", "PE Low", "PE Prev Close", "Expiry Date", "Last Updated At",
                 "Call INTRINSIC", "Call EXTRINSIC", "Put INTRINSIC", "Put EXTRINSIC"]

def write_snapshot(self, snapshot: ChainSnapshot, status: WorkerStatus) -> None:
    self.ensure_layout()
    body = {"valueInputOption": "USER_ENTERED", "data": [
        {"range": "SENSEX!A1:AT3", "values": summary_values(snapshot, status)},
        {"range": f"SENSEX!A6:AT{5 + len(snapshot.rows)}", "values": chain_values(snapshot)},
    ]}
    self._sheets.spreadsheets().values().batchUpdate(spreadsheetId=self._sheet_id, body=body).execute()
```

Use `service_account.Credentials.from_service_account_info(json.loads(secret), scopes=["https://www.googleapis.com/auth/spreadsheets"])`. Set formulas only in intrinsic/extrinsic columns and preserve columns with unavailable source data as empty strings.

- [ ] **Step 4: Run the Task 5 tests**

Run: `python -m pytest tests/test_sheet.py -v`

Expected: PASS.

## Task 6: Worker orchestration, retry behavior, and command line

**Files:**
- Create: `src/sensex_chain/worker.py`
- Create: `src/sensex_chain/cli.py`
- Create: `src/sensex_chain/__main__.py`
- Create: `tests/test_worker.py`

**Interfaces:**
- Consumes all Task 1–5 interfaces through dependency injection.
- Produces `LiveChainWorker.run(segment: SessionSegment) -> int` and CLI command `python -m sensex_chain --segment morning [--dry-run]`.
- Returns `0` for a clean stop, `2` for invalid configuration/authentication, and `3` for unavailable contracts or a persistent Sheets failure.

- [ ] **Step 1: Write a failing worker cadence and reconnect test**

```python
def test_worker_flushes_at_ten_second_cadence_and_stops_at_segment_end(clock, fake_gateway, fake_feed):
    worker.run(SessionSegment.MORNING)
    assert fake_gateway.snapshot_writes == 3
    assert fake_feed.stop_called is True

def test_worker_restarts_a_failed_feed_with_bounded_backoff(clock, fake_feed):
    fake_feed.fail_connect_times = 2
    assert worker.run(SessionSegment.AFTERNOON) == 0
    assert fake_feed.connect_attempts == 3
```

- [ ] **Step 2: Run the worker tests to verify they fail**

Run: `python -m pytest tests/test_worker.py -v`

Expected: FAIL because `sensex_chain.worker` does not exist.

- [ ] **Step 3: Implement the bounded supervisor loop**

```python
def run(self, segment: SessionSegment) -> int:
    end_at = segment.ends_at(self._clock.now())
    chain = self._catalog.current_sensex_chain(self._clock.now().date())
    feeds = [self._feed_factory(self._token_provider.access_token()) for _ in chunk_subscriptions(chain.symbols)]
    try:
        for feed, symbols in zip(feeds, chunk_subscriptions(chain.symbols)):
            feed.start(symbols, self._cache.upsert)
        while self._clock.now() < end_at:
            self._gateway.write_snapshot(self._cache.snapshot(chain, self._clock.now()), WorkerStatus.connected(self._clock.now()))
            self._clock.sleep(min(self._config.flush_seconds, seconds_remaining(self._clock.now(), segment)))
    finally:
        for feed in feeds:
            feed.stop()
    return 0
```

Wrap feed start failures in three attempts with 2, 4, and 8 seconds of backoff, and write a redacted `DISCONNECTED` status before each retry. In `--dry-run`, select the chain and print only counts/expiry/target ranges; do not create socket or Sheets clients.

- [ ] **Step 4: Run worker and full unit test suites**

Run: `python -m pytest -v`

Expected: PASS.

## Task 7: Public-repository workflow and operator documentation

**Files:**
- Create: `.github/workflows/sensex-live.yml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `tests/test_repository_safety.py`

**Interfaces:**
- Consumes the CLI created in Task 6.
- Produces two UTC schedules, a manual-dispatch segment input, reproducible dependency installation, and complete secret/setup guidance.

- [ ] **Step 1: Write a failing static workflow/safety test**

```python
def test_workflow_has_both_required_ist_equivalent_crons():
    workflow = Path(".github/workflows/sensex-live.yml").read_text()
    assert 'cron: "45 3 * * 1-5"' in workflow
    assert 'cron: "45 6 * * 1-5"' in workflow
    assert "FYERS_PIN: ${{ secrets.FYERS_PIN }}" in workflow

def test_production_source_contains_no_trade_api_names():
    source = "\n".join(path.read_text(encoding="utf-8") for path in Path("src/sensex_chain").rglob("*.py"))
    prohibited = ("place_order", "modify_order", "cancel_order", "positions", "funds", "tradebook")
    assert not any(word in source.lower() for word in prohibited)
```


- [ ] **Step 2: Run the repository safety test to verify it fails**

Run: `python -m pytest tests/test_repository_safety.py -v`

Expected: FAIL because the workflow and documentation files do not exist.

- [ ] **Step 3: Implement the workflow and safe operator files**

```yaml
name: SENSEX live option chain
on:
  schedule:
    - cron: "45 3 * * 1-5"
    - cron: "45 6 * * 1-5"
  workflow_dispatch:
    inputs:
      segment:
        type: choice
        required: true
        options: [morning, afternoon]
permissions:
  contents: read
concurrency:
  group: sensex-live-${{ github.event.schedule || inputs.segment }}
  cancel-in-progress: false
jobs:
  stream:
    runs-on: ubuntu-latest
    timeout-minutes: 210
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install .
      - run: python -m sensex_chain --segment "$SEGMENT"
        env:
          SEGMENT: ${{ github.event_name == 'workflow_dispatch' && inputs.segment || github.event.schedule == '45 3 * * 1-5' && 'morning' || 'afternoon' }}
          FYERS_CLIENT_ID: ${{ secrets.FYERS_CLIENT_ID }}
          FYERS_SECRET_KEY: ${{ secrets.FYERS_SECRET_KEY }}
          FYERS_REFRESH_TOKEN: ${{ secrets.FYERS_REFRESH_TOKEN }}
          FYERS_PIN: ${{ secrets.FYERS_PIN }}
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
          GOOGLE_SHEET_ID: ${{ secrets.GOOGLE_SHEET_ID }}
```

Document: creating a Google Cloud service account; enabling Google Sheets API; saving its minified JSON as `GOOGLE_SERVICE_ACCOUNT_JSON`; sharing the supplied Sheet as Editor with the service-account email; adding all six secrets; creating/refreshing the FYERS refresh token at least every 15 days; and GitHub scheduled-run limitations.

- [ ] **Step 4: Run repository safety tests and a dry run**

Run: `python -m pytest tests/test_repository_safety.py -v`

Expected: PASS.

Run: `python -m sensex_chain --segment morning --dry-run`

Expected: exits without contacting FYERS or Google Sheets and prints only the selected configuration-free execution path.

## Task 8: Final verification and handoff

**Files:**
- Modify: `README.md`
- Modify: `tests/test_repository_safety.py`

**Interfaces:**
- Consumes the completed application and workflow from Tasks 1–7.
- Produces evidence that the package tests, dry run, secret scanning, and source safety guard all pass.

- [ ] **Step 1: Add an end-to-end fake dependency test**

```python
def test_fake_socket_to_fake_sheet_flow_never_calls_trading_client(fake_runtime):
    exit_code = LiveChainWorker.from_dependencies(fake_runtime).run(SessionSegment.MORNING)
    assert exit_code == 0
    assert fake_runtime.sheet.snapshot_writes >= 1
    assert fake_runtime.trade_calls == []
```

- [ ] **Step 2: Run the full test suite without pytest cache writes**

Run: `python -m pytest -p no:cacheprovider --basetemp .pytest-tmp -v`

Expected: PASS with all unit, integration-style, workflow, and source-safety tests green.

- [ ] **Step 3: Run syntax and package verification**

Run: `python -m compileall -q src`

Expected: no output and exit code 0.

Run: `python -m pip install . --no-deps`

Expected: package installs from local source without fetching a secret or making an FYERS/Google API call.

- [ ] **Step 4: Inspect the rendered public-repository configuration manually**

Check that `.env.example` contains only variable names and placeholders, `README.md` does not reproduce a secret, and `.github/workflows/sensex-live.yml` references every secret through `${{ secrets.NAME }}`.

## Plan self-review

- Spec coverage: Tasks 1 and 6 implement IST split-session exits; Task 2 implements master-derived expiry; Tasks 3 and 4 implement WebSocket data and failure isolation; Task 5 implements the Google Sheet batches/layout; Task 7 implements public GitHub schedules and secret guidance; Task 8 validates data-only behavior and no-secret handoff.
- Placeholder scan: no deferred implementation markers are present. Every test and production step contains an executable command or concrete implementation boundary.

- Type consistency: `RuntimeConfig`, `SessionSegment`, `CurrentExpiryChain`, `FyersTokenProvider`, `FyersDataFeed`, `LatestMarketCache`, `ChainSnapshot`, `GoogleSheetGateway`, and `LiveChainWorker` are defined before their later-task consumers.
