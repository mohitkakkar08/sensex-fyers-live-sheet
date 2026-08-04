# SENSEX FYERS Live Option Chain

This market-data-only worker streams the nearest valid BSE SENSEX option expiry into one Google Sheet every 10 seconds. It does not place, modify, cancel, or inspect trades.

## One-time setup

1. In Google Cloud, create a service account, enable the **Google Sheets API**, and create a JSON key.
2. Share the target sheet as **Editor** with the service-account email in that JSON key. The target tab must be named `SENSEX`.
3. In FYERS, enable **External 2FA/TOTP** and retain the base32 setup secret securely. The worker generates the current TOTP only in memory.
4. In your GitHub repository, open **Settings > Secrets and variables > Actions > New repository secret**. Add exactly these eight secrets:
   - `FYERS_CLIENT_ID`
   - `FYERS_SECRET_KEY`
   - `FYERS_USER_ID`
   - `FYERS_PIN`
   - `FYERS_TOTP_SECRET`
   - `FYERS_REDIRECT_URI` - set this to the registered value: `https://127.0.0.1/`
   - `GOOGLE_SERVICE_ACCOUNT_JSON` - the complete minified JSON key
   - `GOOGLE_SHEET_ID`
5. Open **Actions > SENSEX live option chain > Run workflow**, select `morning`, and inspect the generic run result. Do not add token-printing steps or share workflow logs that could expose secrets.

Each scheduled job creates a fresh FYERS session automatically. It does not save an access token or require a daily token update. The automated browserless login is isolated in one module; if FYERS changes its authentication service, the run fails safely and that module may need to be updated.

## Schedule

The workflow uses UTC schedules `45 3 * * 1-5` (09:15 IST) and `45 6 * * 1-5` (12:15 IST). The Python worker stops at 12:15 and 15:30 IST. GitHub scheduled workflows can be delayed, so monitor the Actions history and the `Status` row in the `SENSEX` tab. Python dependencies are cached between successful GitHub runs to reduce startup time. Each live cycle is deadline-scheduled, so normal API and Sheets latency does not add to the 10-second refresh interval.

## SENSEX tab layout and diagnostics

The worker writes the option chain in columns **A:AL**, mirroring the supplied CE / Strike / PE layout: CE market data, the central strike, then PE market data, timestamp, and both VWAP fields. One FYERS websocket carries the index, India VIX, and all current-expiry contracts. It supplies OHLC, LTP, volume, and VWAP. A rate-limited, bounded FYERS Option Chain call supplements OI, OI change, IV, and Greeks (`Delta`, `Gamma`, `Vega`, `Theta`, `Rho`) for every strike in the selected expiry.

Row 4 reports `Status`, a safe `Diagnostic` code, total tick count, option tick count, expiry, and update time. `LIVE` means the websocket is currently healthy and both index and option ticks have been received. A socket closure/error, incomplete market coverage, or an option-chain issue is shown as `PARTIAL_LIVE`; the displayed values are not falsely labelled as live. A transient Google Sheets write error is retried on the next 10-second cycle. Old rows below a smaller subsequent chain are cleared. Static column headers are written once per worker run; every subsequent update uses the same layout with a smaller raw-value payload.

GitHub Actions logs the configuration, instrument-catalog, Google-Sheets, and FYERS-authentication stages. These diagnostics never print credentials, PINs, TOTP values, authorization codes, or access tokens.

## Local verification

```powershell
python -m pytest -p no:cacheprovider --basetemp work\pytest-tmp -v
python -m compileall -q src
python -m sensex_chain --segment morning --dry-run
```

Do not commit `.env`, service-account JSON, FYERS PIN, TOTP secret, authorization codes, refresh tokens, or access tokens.