"""Lanca o server.py com banco sqlite TEMPORARIO (isolado), codigo atual."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

PASTA = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PASTA))

import models  # noqa: E402

models.DB_PATH = pathlib.Path(tempfile.mkdtemp(prefix="eap_test_")) / "test.db"

import server  # noqa: E402  (init_db/seed ocorrem no import, no DB temporario)

if __name__ == "__main__":
    server.main()
