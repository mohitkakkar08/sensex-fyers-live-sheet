# SENSEX Futures Feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream the nearest unexpired BSE SENSEX futures contract alongside the current-expiry option chain and write it to `SENSEX!L:Z`.

**Architecture:** Reuse the downloaded BSE FO catalog, existing single FYERS socket, cache, and batched Google Sheets write. Extend the immutable chain selection with an optional `FutureContract`, then add a future summary block in the gateway.

**Tech Stack:** Python 3.12, FYERS API v3 websocket, Google Sheets API v4, pytest.

## Global Constraints

- Keep a single FYERS websocket and the ten-second refresh cadence.
- Do not add credentials, logs, or extra REST polling.
- Leave the option-chain columns `A:AL` unchanged.
- Do not stage generated `build/` files or pre-existing untracked documentation.

---

### Task 1: Discover and subscribe to the current SENSEX future

**Files:**
- Modify: `src/sensex_chain/instruments.py`, `src/sensex_chain/cache.py`
- Test: `tests/test_instruments.py`, `tests/test_cache.py`

- [ ] **Step 1: Write failing tests** for a fixture containing two unexpired SENSEX futures. Assert the nearest contract is selected, appears in `CurrentExpiryChain.symbols`, and is available from a cache snapshot.
- [ ] **Step 2: Run the focused tests** with `python -m pytest -p no:cacheprovider tests/test_instruments.py tests/test_cache.py -q`; verify they fail because futures are not modelled.
- [ ] **Step 3: Implement minimal parsing and snapshot support** using `FutureContract` and `CurrentExpiryChain.future`.
- [ ] **Step 4: Re-run focused tests** and confirm they pass.

### Task 2: Write futures values to the SENSEX summary block

**Files:**
- Modify: `src/sensex_chain/sheet.py`
- Test: `tests/test_sheet.py`

- [ ] **Step 1: Write a failing test** asserting `L1:Z2` contains the requested headings and a future tick's LTP, volume, OI, OI change, OI change %, and VWAP.
- [ ] **Step 2: Run** `python -m pytest -p no:cacheprovider tests/test_sheet.py -q` and verify the new assertion fails.
- [ ] **Step 3: Implement the future header/value block** while retaining the existing `A:AL` option layout and one `batchUpdate` request.
- [ ] **Step 4: Re-run the focused test** and confirm it passes.

### Task 3: End-to-end validation and publication

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document** the new live future block and its no-extra-socket behaviour.
- [ ] **Step 2: Run** `python -m pytest -p no:cacheprovider --basetemp work\\pytest-tmp -q`, `python -m compileall -q src`, `python -m sensex_chain --segment morning --dry-run`, and `git diff --check`.
- [ ] **Step 3: Commit and push** only the source, tests, README, and these two futures design documents.
