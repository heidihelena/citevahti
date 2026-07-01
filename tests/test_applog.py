"""``applog.py`` — one idempotent rotating log file per component."""

from __future__ import annotations

import logging

from citevahti import applog


def test_get_logger_creates_log_dir_and_writes(tmp_path, monkeypatch):
    monkeypatch.setattr("citevahti.paths.log_dir", lambda: tmp_path / "Logs" / "CiteVahti")
    logger = applog.get_logger("app-test-1")
    logger.info("hello")
    for h in logger.handlers:
        h.flush()
    log_file = tmp_path / "Logs" / "CiteVahti" / "app-test-1.log"
    assert log_file.is_file()
    assert "hello" in log_file.read_text()


def test_get_logger_is_idempotent_no_duplicate_handlers(tmp_path, monkeypatch):
    monkeypatch.setattr("citevahti.paths.log_dir", lambda: tmp_path / "Logs" / "CiteVahti")
    first = applog.get_logger("app-test-2")
    n_handlers = len(first.handlers)
    second = applog.get_logger("app-test-2")
    assert second is first
    assert len(second.handlers) == n_handlers


def test_get_logger_falls_back_to_null_handler_on_oserror(monkeypatch):
    def _boom():
        raise OSError("no permission")

    monkeypatch.setattr("citevahti.paths.log_dir", _boom)
    logger = applog.get_logger("app-test-3")
    assert any(isinstance(h, logging.NullHandler) for h in logger.handlers)
    logger.info("should not raise")
