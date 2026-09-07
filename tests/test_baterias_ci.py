"""Integracao: roda as baterias funcionais (cada uma sobe um servidor isolado).

Essas baterias são os mesmos roteiros usados nas fases A/B — em CI elas
garantem que o contrato MCP completo permanece verde.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

BATERIAS = [
    "_teste_planejamento.py",   # visao engenheiro de planejamento (26 casos)
    "_teste_multiprojeto.py",   # Fase A: multi-obra (32 casos)
    "_teste_semantica.py",      # Fase B: avisos semanticos (9 casos)
    "_teste_f11.py",            # F1.1: uid estavel + eap_id_history (8 casos)
]


@pytest.mark.integracao
@pytest.mark.parametrize("script", BATERIAS)
def test_bateria_funcional(script):
    # Roteiros A/B pre-datam o strict single root (F1.2): exercitam o ramo
    # aviso. O ramo problema (producao) tem cobertura unitaria dedicada.
    env = dict(os.environ, EAP_STRICT_SINGLE_ROOT="0")
    proc = subprocess.run(
        [sys.executable, script],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=420,
        env=env,
    )
    assert proc.returncode == 0, (
        f"{script} FALHOU (rc={proc.returncode})\n"
        f"--- stdout ---\n{proc.stdout[-4000:]}\n"
        f"--- stderr ---\n{proc.stderr[-2000:]}"
    )
