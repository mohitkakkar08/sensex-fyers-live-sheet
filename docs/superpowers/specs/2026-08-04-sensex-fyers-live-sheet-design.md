# SENSEX FYERS Live Option Chain to Google Sheets

## Objective

Update the Google Sheet `1WIESkL_j-XRDi0vH4eybi3ZaZp89qkvPPv1UZGtYnlQ` with live BSE SENSEX current-expiry option-chain data every 10 seconds during normal market hours.  The deployment is a public GitHub repository using encrypted GitHub Actions secrets.  The integration is market-data-only and must never call an order, position, funds, or trading endpoint.

## Operating model

Two GitHub-hosted Ubuntu workflow jobs run on weekdays (all times IST):

| Run | Scheduled start | Controlled stop | UTC cron |
| --- | --- | --- | --- |
| Morning | 09:15 | 12:15 | `45 3 * * 1-5` |
| Afternoon | 12:15 | 15:30 | `45 6 * * 1-5` |

The worker itself applies the IST end time and exits cleanly even when a GitHub schedule starts late.  It records the status and last-successful sheet write.  A delayed or missing GitHub scheduled run is visible in Actions and in the sheet status; GitHub scheduling is best effort, not an execution guarantee.

## Data path

1. Load the FYERS BSE instrument master at each job start.
2. Identify `BSE:SENSEX-INDEX` and the nearest available SENSEX option expiry with both calls and puts.  Do not generate symbols from a fixed Thursday rule; this protects against holiday-shifted expiries.
3. Subscribe to the index and selected current-expiry contracts using FYERS API v3 Data WebSocket `symbolUpdate` mode.  Keep an in-memory cache and reconnect with bounded exponential backoff.
4. Every 10 seconds, convert the cache into one rectangular batch and update the Google Sheets API once.  Batch writes avoid one API call per instrument.
5. The output uses a `SENSEX` tab: underlying summary at the top, CE/strike/PE chain below, data timestamp, expiry, and worker health.  Intrinsic and extrinsic values are spreadsheet formulas.

The implementation will map all fields provided by FYERS.  A field not supplied by the selected FYERS feed (for example a Greek, if unavailable) is left blank and labelled as unavailable; it is never invented or estimated.

## Authentication and secret boundary

The public repository contains only source code, dependency lockfiles, workflow definitions, and documentation.  It contains no credentials or spreadsheet data.

| Secret | Purpose |
| --- | --- |
| `FYERS_CLIENT_ID` | FYERS API application identifier |
| `FYERS_SECRET_KEY` | FYERS application secret |
| `FYERS_REFRESH_TOKEN` | Supported FYERS session renewal input |
| `FYERS_PIN` | FYERS PIN required only by the refresh-token exchange |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google service account credential JSON |
| `GOOGLE_SHEET_ID` | Target spreadsheet identifier |

The service-account email inside `GOOGLE_SERVICE_ACCOUNT_JSON` must be shared as an Editor on the target sheet.  FYERS login password, OTP, and TOTP are explicitly out of scope and will not be stored or automated. `FYERS_PIN` is stored only as an encrypted GitHub Secret and is supplied only to the documented refresh-token exchange. If FYERS refresh-token rotation requires a new stored refresh token, the operator updates the corresponding GitHub secret.

## Safety and recovery

- No trading calls or trading permissions are requested by the code.
- Request and message parsing is validated; malformed ticks are ignored and logged without secrets.
- WebSocket reconnects use a capped retry policy; the worker continues only until the planned session end.
- An invalid/missing expiry or an empty subscription is a visible failure, not a silent empty overwrite.
- Google Sheets write failures retain cached data and retry at the next 10-second cycle.
- GitHub concurrency controls prevent duplicate runs for the same segment.

## Verification

- Unit tests cover expiry selection, SENSEX-symbol filtering, tick normalization, batch range formation, timing boundaries, and credential redaction.
- A fake FYERS socket and fake Sheets gateway test the worker without external credentials.
- A dry-run mode emits the planned writes but performs no FYERS or Google Sheets calls.
- A final static check verifies that production source imports no FYERS trade/order client methods.

## Known operating constraints

- GitHub Actions schedules can be delayed or dropped under load; they are suitable here only because the user accepts a zero-cost, informational feed with this limitation.
- Private-repository GitHub-hosted minutes are insufficient for this schedule; the repository is intentionally public and all secrets remain GitHub Secrets.
- FYERS access/session validity is broker-controlled.  A valid supported renewal credential is required at run time.
