# SENSEX FYERS Live Option Chain

This is a market-data-only worker that streams the nearest valid BSE SENSEX option expiry into one Google Sheet every 10 seconds. It does not place, modify, cancel, or inspect trades.

## Before deployment

1. In Google Cloud, create a service account, enable **Google Sheets API**, and create a JSON key.
2. Share the target sheet as **Editor** with the service-account email in that JSON file.
3. Create a public GitHub repository and add these Actions secrets:
   - `FYERS_CLIENT_ID`
   - `FYERS_SECRET_KEY`
   - `FYERS_REFRESH_TOKEN`
   - `FYERS_PIN`
   - `GOOGLE_SERVICE_ACCOUNT_JSON` (the complete, minified JSON key)
   - `GOOGLE_SHEET_ID`
4. Generate a fresh FYERS refresh token before it expires; FYERS documents a 15-day refresh-token validity.

The workflow uses UTC schedules `45 3 * * 1-5` (09:15 IST) and `45 6 * * 1-5` (12:15 IST). The Python worker stops at 12:15 and 15:30 IST. GitHub scheduled workflows can be delayed, so monitor the Actions history and `Status` row in the SENSEX tab.

## Local verification

```powershell
python -m pytest -p no:cacheprovider --basetemp work\pytest-tmp -v
python -m sensex_chain --segment morning --dry-run
```

Do not commit `.env`, service-account JSON, FYERS PIN, access tokens, or refresh tokens.
