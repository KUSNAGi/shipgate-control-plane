from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from shipgate.cli import audit_check, bootstrap
from shipgate.db import build_engine


def test_cli_provisions_once_and_verifies_audit(tmp_path, monkeypatch, capsys):
    url = f"sqlite:///{tmp_path / 'bootstrap.sqlite3'}"
    monkeypatch.setenv("SHIPGATE_DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")

    assert bootstrap("dev-team", "first-admin") == 0
    output = capsys.readouterr().out
    assert "sg_" in output and "shown ONCE" in output
    assert bootstrap("dev-team", "first-admin") == 2
    assert "sg_" not in capsys.readouterr().out
    assert audit_check("dev-team") == 0
    assert "valid=true" in capsys.readouterr().out


def test_migration_up_down_roundtrip(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'roundtrip.sqlite3'}"
    monkeypatch.setenv("SHIPGATE_DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = build_engine(url)
    assert "releases" in inspect(engine).get_table_names()
    command.downgrade(config, "base")
    assert "releases" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    assert "releases" in inspect(engine).get_table_names()
    engine.dispose()
