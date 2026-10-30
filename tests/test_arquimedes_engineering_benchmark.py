"""Arquimedes Engineering Benchmark — EAP: isolated ephemeral SQLite fixtures.

Reference comparison is explicit: a finite scope list is the only basis
for completeness; structural correctness alone never proves 100%.
"""
import pytest


def _node(db, code, parent, project="P-BENCH"):
    return db.inserir_nodo({
        "project_id": project, "eap_id": code, "parent_id": parent,
        "nivel": code.count(".")+1, "frente_id": "F1",
        "local_id": "L1", "tipo_frente": "fundacao",
        "nome": "Servico "+code, "unidade": "conj", "quantidade": None
    })


def test_scope_reference_omission_then_exact_full_coverage(db, record_property):
    _node(db, "1", None)
    _node(db, "1.1", "1")
    a = db.criar_item_escopo("Servico A", "P-BENCH", code="ES-01", fonte="escopo-ficticio")
    b = db.criar_item_escopo("Servico B", "P-BENCH", code="ES-02", fonte="escopo-ficticio")
    db.vincular_escopo_eap(a["scope_id"], "1", "P-BENCH")
    partial = db.validar_100_porcento("P-BENCH")
    assert partial["percentual_cobertura"] == 50
    assert partial["status"] == "REPROVADA"
    assert [x["scope_id"] for x in partial["escopo_sem_eap"]] == [b["scope_id"]]
    db.vincular_escopo_eap(b["scope_id"], "1.1", "P-BENCH")
    full = db.validar_100_porcento("P-BENCH")
    assert full["percentual_cobertura"] == 100
    assert full["status"] == "APROVAVEL"
    record_property("expected", '{"initial_coverage":50,"final_coverage":100}')
    record_property("obtained", f'{{"initial_coverage":{partial["percentual_cobertura"]},"final_coverage":{full["percentual_cobertura"]}}}')
    record_property("difference", "0")
    record_property("tolerance", "0"


def test_primary_scope_binding_cannot_be_silently_reassigned(db):
    _node(db, "1", None)
    _node(db, "1.1", "1")
    s = db.criar_item_escopo("Ficticio", "P-BENCH", code="ES-01")
    first = db.vincular_escopo_eap(s["scope_id"], "1.1", "P-BENCH")
    same = db.vincular_escopo_eap(s["scope_id"], "1.1", "P-BENCH")
    assert same["eap_uid"] == first["eap_uid"]
    assert len(db.listar_coberturas("P-BENCH")) == 1
    with pytest.raises(ValueError, match="já possui vínculo principal"):
        db.vincular_escopo_eap(s["scope_id"], "1", "P-BENCH")
    assert len(db.listar_coberturas("P-BENCH")) == 1
    assert db.listar_coberturas("P-BENCH")[0]["eap_uid"] == first["eap_uid"]


def test_move_preserves_uid_and_project_isolation(db):
    _node(db, "1", None)
    _node(db, "1.1", "1")
    _node(db, "2", None)
    original = db.buscar_por_eap_id("1.1", "P-BENCH")
    db.mover_nodo("1.1", "2", "P-BENCH")
    moved = db.buscar_por_eap_id("2.1", "P-BENCH")
    assert moved["uid"] == original["uid"]
    _node(db, "1", None, "P-OUTRO")
    assert db.buscar_por_eap_id("1", "P-OUTRO")["uid"] != moved["uid"]
    assert db.buscar_por_eap_id("2.1", "P-OUTRO") is None


def test_no_scope_reference_must_never_mean_complete(db):
    _node(db, "1", None)
    result = db.validar_100_porcento("P-BENCH")
    assert result["status"] == "SEM_BASE_DE_ESCOPO"
    assert result["percentual_cobertura"] == 0
