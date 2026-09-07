"""Fase 2 / aceite §4.5 - buscar_eap_node: acento e caixa ignorados (§3)."""
from __future__ import annotations

from conftest import nos_de_teste


def _no_escavacao(db, pid: str = "default") -> None:
    db.inserir_nodo({"project_id": pid, "eap_id": "1.1.2", "parent_id": "1.1",
                     "nivel": 3, "frente_id": "FR-001", "local_id": "BL-A",
                     "tipo_frente": "fundacao", "nome": "ESCAVAÇÃO SAPATAS",
                     "unidade": "m³", "quantidade": 1280.0})


def test_buscar_sem_acento_acha_caixa_alta_com_acento(db):
    nos_de_teste(db)
    _no_escavacao(db)
    r = db.buscar_eap_node("escavacao")
    assert [n["eap_id"] for n in r] == ["1.1.2"]
    assert r[0]["nome"] == "ESCAVAÇÃO SAPATAS"


def test_buscar_ignora_caixa_e_acento_no_termo(db):
    nos_de_teste(db)
    assert [n["eap_id"] for n in db.buscar_eap_node("CONCRETO SAPATAS")] == ["1.1.1"]
    assert any(n["eap_id"] == "1" for n in db.buscar_eap_node("FUNDAÇÕES"))


def test_buscar_por_eap_id_frente_local_e_substring(db):
    nos_de_teste(db)
    assert [n["eap_id"] for n in db.buscar_eap_node("1.1.1")] == ["1.1.1"]
    assert len(db.buscar_eap_node("FR-001")) == 3
    assert {n["eap_id"] for n in db.buscar_eap_node("BL-A")} == {"1", "1.1", "1.1.1"}
    assert [n["eap_id"] for n in db.buscar_eap_node("pata")] == ["1.1", "1.1.1"]


def test_buscar_por_responsavel(db):
    nos_de_teste(db)
    db.atualizar_nodo("1.1.1", {"project_id": "default",
                                "responsavel": "João da Silva"})
    r = db.buscar_eap_node("joao")
    assert [n["eap_id"] for n in r] == ["1.1.1"]


def test_buscar_isolada_por_projeto_e_termo_vazio(db):
    nos_de_teste(db)
    db.inserir_nodo({"project_id": "OUTRO", "eap_id": "1", "parent_id": None,
                     "nivel": 1, "frente_id": "FR-X", "tipo_frente": "estrutura",
                     "nome": "Fundacoes outras", "unidade": "conj",
                     "quantidade": None})
    assert [n["eap_id"] for n in db.buscar_eap_node("outras", "OUTRO")] == ["1"]
    assert [n["eap_id"] for n in db.buscar_eap_node("outras", "default")] == []
    assert db.buscar_eap_node("   ") == []
