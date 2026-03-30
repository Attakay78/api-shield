"""Tests for switchly.core.config — the shared engine/backend factory."""

from __future__ import annotations

import pytest

from switchly.core.backends.file import FileBackend
from switchly.core.backends.memory import MemoryBackend
from switchly.core.config import make_backend, make_engine

# Pass config_file="" to all tests that should ignore the project .switchly file.
_NO_CFG = ""


def test_make_backend_memory_explicit():
    backend = make_backend(backend_type="memory")
    assert isinstance(backend, MemoryBackend)


def test_make_backend_memory_default(monkeypatch):
    """Without env vars or a config file the default is memory."""
    monkeypatch.delenv("SWITCHLY_BACKEND", raising=False)
    backend = make_backend(config_file=_NO_CFG)
    assert isinstance(backend, MemoryBackend)


def test_make_backend_file_explicit(tmp_path):
    backend = make_backend(backend_type="file", file_path=str(tmp_path / "s.json"))
    assert isinstance(backend, FileBackend)


def test_make_backend_file_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SWITCHLY_BACKEND", "file")
    monkeypatch.setenv("SWITCHLY_FILE_PATH", str(tmp_path / "s.json"))
    backend = make_backend()
    assert isinstance(backend, FileBackend)


def test_make_backend_from_dot_switchly_file(tmp_path):
    """Values in a .switchly file are respected."""
    cfg_file = tmp_path / ".switchly"
    state_file = tmp_path / "state.json"
    cfg_file.write_text(f"SWITCHLY_BACKEND=file\nSWITCHLY_FILE_PATH={state_file}\n")
    backend = make_backend(config_file=str(cfg_file))
    assert isinstance(backend, FileBackend)


def test_dot_switchly_file_env_var_takes_priority(tmp_path, monkeypatch):
    """`os.environ` wins over the .switchly file."""
    cfg_file = tmp_path / ".switchly"
    cfg_file.write_text("SWITCHLY_BACKEND=file\n")
    monkeypatch.setenv("SWITCHLY_BACKEND", "memory")
    backend = make_backend(config_file=str(cfg_file))
    assert isinstance(backend, MemoryBackend)


def test_dot_switchly_ignores_comments(tmp_path):
    cfg_file = tmp_path / ".switchly"
    cfg_file.write_text("# this is a comment\nSWITCHLY_BACKEND=memory\n")
    backend = make_backend(config_file=str(cfg_file))
    assert isinstance(backend, MemoryBackend)


def test_make_backend_unknown_raises():
    with pytest.raises(ValueError, match="Unknown SWITCHLY_BACKEND"):
        make_backend(backend_type="postgres")


def test_make_engine_default_env(monkeypatch):
    monkeypatch.delenv("SWITCHLY_ENV", raising=False)
    engine = make_engine(backend_type="memory")
    assert engine.current_env == "dev"


def test_make_engine_env_from_arg():
    engine = make_engine(backend_type="memory", current_env="staging")
    assert engine.current_env == "staging"


def test_make_engine_env_from_envvar(monkeypatch):
    monkeypatch.setenv("SWITCHLY_ENV", "dev")
    engine = make_engine(backend_type="memory")
    assert engine.current_env == "dev"


def test_make_engine_returns_switchly_engine():
    from switchly.core.engine import SwitchlyEngine

    engine = make_engine(backend_type="memory")
    assert isinstance(engine, SwitchlyEngine)


def test_cli_and_app_use_same_file_backend(tmp_path, monkeypatch):
    """Engine built by CLI factory and app factory read/write the same file."""
    import anyio

    file_path = str(tmp_path / "shared.json")
    monkeypatch.setenv("SWITCHLY_BACKEND", "file")
    monkeypatch.setenv("SWITCHLY_FILE_PATH", file_path)

    async def _run():
        # Simulate app registering and then disabling a route.
        app_engine = make_engine()
        await app_engine.register("/api/pay", {"status": "active"})
        await app_engine.disable("/api/pay", reason="migration")

        # Simulate CLI reading state from the same file.
        cli_engine = make_engine()
        state = await cli_engine.get_state("/api/pay")
        assert state.status == "disabled"
        assert state.reason == "migration"

    anyio.run(_run)
