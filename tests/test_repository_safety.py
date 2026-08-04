from __future__ import annotations

from pathlib import Path


def test_workflow_has_required_schedules_and_automated_login_secret_references() -> None:
    workflow = Path(".github/workflows/sensex-live.yml").read_text(encoding="utf-8")

    assert 'cron: "45 3 * * 1-5"' in workflow
    assert 'cron: "45 6 * * 1-5"' in workflow
    for name in ("FYERS_USER_ID", "FYERS_TOTP_SECRET", "FYERS_REDIRECT_URI"):
        assert f"{name}: ${{{{ secrets.{name} }}}}" in workflow
    assert "FYERS_REFRESH_TOKEN: ${{ secrets.FYERS_REFRESH_TOKEN }}" not in workflow
    assert "GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}" in workflow


def test_production_source_contains_no_trade_api_names() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("src/sensex_chain").rglob("*.py")
    ).lower()
    prohibited = ("place_order", "modify_order", "cancel_order", "tradebook", "holdings", "funds")

    assert not any(word in source for word in prohibited)
