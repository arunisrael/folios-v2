from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from folios_v2.cli.app import app
from folios_v2.cli.deps import reset_container


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_url = f"sqlite+aiosqlite:///{tmp_path/'cli.db'}"
    monkeypatch.setenv("FOLIOS_DATABASE_URL", db_url)
    monkeypatch.setenv("FOLIOS_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("FOLIOS_ENV", "test")
    reset_container()


def test_cli_seed_and_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "seed-strategy",
            "Momentum",
            "Study",
            "--tickers",
            "AAPL,MSFT",
        ],
    )
    assert result.exit_code == 0
    created_id = result.stdout.strip().split()[-1]

    list_result = runner.invoke(app, ["list-strategies"])
    assert list_result.exit_code == 0
    assert "Momentum" in list_result.stdout

    ensure_result = runner.invoke(app, ["ensure-schedule", created_id])
    assert ensure_result.exit_code == 0
    assert "weekday" in ensure_result.stdout

    plan_result = runner.invoke(app, ["plan-week", "2025", "10"])
    assert plan_result.exit_code == 0


def test_cli_show_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["show-settings"])
    assert result.exit_code == 0
    assert "Environment:\t" in result.stdout
