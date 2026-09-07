"""Config de testes: isola o banco (sqlite temporario) e nunca usa Turso."""
from __future__ import annotations

import os

# Garante que os testes locais nunca toquem o Turso de producao.
os.environ.pop("TURSO_URL", None)
os.environ.pop("TURSO_TOKEN", None)
# Roteiros das fases A/B pre-datam o F1.2 (raiz unica): montam arvores com
# multiplas raizes e exercitam o ramo AVISO do validar_estrutura. O ramo
# PROBLEMA (strict, default de producao desde ac6746d) e coberto por
# test_validar_strict_multi_root (test_models_unit) e pelo aceite do Passo 5.
os.environ["EAP_STRICT_SINGLE_ROOT"] = "0"

import pytest  # noqa: E402

import models  # noqa: E402


@pytest.fixture()
def db(monkeypatch, tmp_path):
    """Banco sqlite temporario e limpo para cada teste (camada models)."""
    monkeypatch.setattr(models, "DB_PATH", tmp_path / "teste.db")
    models.init_db()
    return models


def nos_de_teste(models_mod) -> None:
    """Monta a arvore base usada nos testes: raiz 1 (fundacao) + subnos."""
    m = models_mod
    m.inserir_nodo({"eap_id": "1", "parent_id": None, "nivel": 1,
                    "frente_id": "FR-001", "local_id": "BL-A",
                    "tipo_frente": "fundacao", "nome": "Fundacoes",
                    "unidade": "conj", "quantidade": None})
    m.inserir_nodo({"eap_id": "1.1", "parent_id": "1", "nivel": 2,
                    "frente_id": "FR-001", "local_id": "BL-A",
                    "tipo_frente": "fundacao", "nome": "Sapatas",
                    "unidade": "conj", "quantidade": None})
    m.inserir_nodo({"eap_id": "1.1.1", "parent_id": "1.1", "nivel": 3,
                    "frente_id": "FR-001", "local_id": "BL-A",
                    "tipo_frente": "fundacao", "nome": "Concreto sapatas",
                    "unidade": "m³", "quantidade": 12.0})
    m.inserir_nodo({"eap_id": "2", "parent_id": None, "nivel": 1,
                    "frente_id": "FR-002", "local_id": "BL-B",
                    "tipo_frente": "estrutura", "nome": "Estrutura",
                    "unidade": "conj", "quantidade": None})
