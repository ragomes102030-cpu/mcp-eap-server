from __future__ import annotations

from models.db import _coluna_ja_existe, _turso_ddl_sem_resultado


def test_turso_ddl_sem_resultado_detects_legacy_client_error():
    assert _turso_ddl_sem_resultado(KeyError("result")) is True
    assert _turso_ddl_sem_resultado(KeyError("rows")) is False
    assert _turso_ddl_sem_resultado(RuntimeError("result")) is False


def test_coluna_ja_existe_keeps_idempotent_error_detection():
    assert _coluna_ja_existe(RuntimeError("duplicate column name: status")) is True
    assert _coluna_ja_existe(RuntimeError("database is locked")) is False
