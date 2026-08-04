# Live Worker Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the existing 10-second live-data contract while reducing cadence drift, Sheet payload work, and repeated option-chain metadata allocation.

**Architecture:** The worker will schedule each cycle against a monotonic deadline rather than sleeping a fixed ten seconds after work. The Sheet gateway will write static headers only once per process and raw scalar values thereafter. Current-expiry lookup structures will be cached in the worker and supplied to snapshot/enrichment calls without rebuilding contract-symbol sets per refresh.

**Tech Stack:** Python 3.12, FYERS API v3 websocket/REST, Google Sheets API v4, pytest, GitHub Actions.

## Global Constraints

- Keep the public 10-second Sheet-refresh contract and all existing sheet columns.
- Keep one FYERS option-chain request per live cycle and the existing rate-limit gate.
- Do not log or persist credentials, tokens, PINs, TOTP values, or raw FYERS responses.
- Do not stage or commit the generated `build/` folder.

---

### Task 1: Deadline-based worker cadence

**Files:**
- Modify: `src/sensex_chain/worker.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Produces: `Clock.monotonic() -> float` and worker sleep duration calculated from the next deadline.

- [x] **Step 1: Write failing tests**

```python
assert clock.sleeps == [7]
```

Use a clock where REST plus Sheet work consumes three seconds; assert a ten-second cadence sleeps seven seconds, not ten.

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -p no:cacheprovider tests/test_worker.py -q`
Expected: FAIL because the current worker always sleeps `flush_seconds` after work.

- [x] **Step 3: Write minimal implementation**

Track the cycle start with `clock.monotonic()`, advance one deadline by `flush_seconds` after every attempted cycle, and sleep only until that deadline. If a cycle overruns, advance missed deadlines without a catch-up burst.

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest -p no:cacheprovider tests/test_worker.py -q`
Expected: PASS.

### Task 2: Lean Google Sheets payloads

**Files:**
- Modify: `src/sensex_chain/sheet.py`
- Test: `tests/test_sheet.py`

**Interfaces:**
- Produces: static headers written on the first snapshot only; subsequent writes contain summary and data rows only.

- [x] **Step 1: Write failing test**

```python
first_data = service.last_body["data"]
gateway.write_snapshot(snapshot(), status)
assert service.last_body["data"][1]["range"] == "SENSEX!A7:AL7"
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -p no:cacheprovider tests/test_sheet.py -q`
Expected: FAIL because every update currently writes row 6 headers.

- [x] **Step 3: Write minimal implementation**

Use a gateway-local boolean to include the header row only on the first successful `batchUpdate`; use `RAW` values because the worker emits typed values and preformatted timestamps.

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest -p no:cacheprovider tests/test_sheet.py -q`
Expected: PASS.

### Task 3: Reuse full-expiry selection metadata

**Files:**
- Modify: `src/sensex_chain/cache.py`, `src/sensex_chain/option_chain.py`
- Test: `tests/test_cache.py`, `tests/test_option_chain.py`

**Interfaces:**
- Produces: a `CurrentExpiryChain` cached strike-pair plan and option-symbol set reusable by snapshot and option-chain enrichment.

- [x] **Step 1: Write failing tests**

```python
assert chain.option_symbols == frozenset({...})
assert chain.rows_by_strike[Decimal("80000")]["CE"].symbol == "...CE"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -p no:cacheprovider tests/test_cache.py tests/test_option_chain.py -q`
Expected: FAIL because the current code rebuilds both structures every ten-second cycle.

- [x] **Step 3: Write minimal implementation**

Construct immutable properties once on `CurrentExpiryChain`; have `LatestMarketCache.snapshot()` and `FyersOptionChainEnricher.refresh()` consume them.

- [x] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -p no:cacheprovider tests/test_cache.py tests/test_option_chain.py -q`
Expected: PASS.

### Task 4: Integration verification and publication

**Files:**
- Modify: `README.md`

- [x] **Step 1: Update operating documentation**

Document the fixed cadence and first-write header behavior without changing the user-facing layout or live-data interval.

- [x] **Step 2: Run final validation**

Run: `python -m pytest -p no:cacheprovider -q`; `python -m compileall -q src`; `PYTHONPATH=src python -m sensex_chain --segment morning --dry-run`; `git diff --check`.

- [x] **Step 3: Commit and push**

Stage only the named source, tests, README, and plan; commit with `perf: optimize live update cadence`; push to `main`.
