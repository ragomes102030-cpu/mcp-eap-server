"""F1.1 - uid estavel: cria, move preserva uid, eap_id_history, ciclo."""
from __future__ import annotations

import pytest

from conftest import nos_de_teste


def test_criar_gera_uid_unico(db):
    nos_de_teste(db)
    uids = [db.buscar_por_eap_id(e, "default")["uid"] for e in ("1", "1.1", "1.1.1", "2")]
    assert all(uids)
    assert len(set(uids)) == 4  # todos distintos


def test_move_preserva_uid_e_grava_history(db):
    nos_de_teste(db)
    uid_filho = db.buscar_por_eap_id("1.1", "default")["uid"]
    uid_neto = db.buscar_por_eap_id("1.1.1", "default")["uid"]

    mov = db.mover_nodo("1.1", "2", "default", motivo="reorganizacao de frentes")
    assert mov["eap_id"] == "2.1"
    assert mov["nivel"] == 2

    # uid NAO mudou apos o move
    atual = db.buscar_por_uid(uid_filho, "default")
    assert atual is not None
    assert atual["eap_id"] == "2.1"
    neto = db.buscar_por_uid(uid_neto, "default")
    assert neto["eap_id"] == "2.1.1"
    assert neto["parent_id"] == "2.1"

    # eap_id antigo nao existe mais como no
    assert db.buscar_por_eap_id("1.1", "default") is None

    # history registrou de/para
    hist = db.historico_movimentos(project_id="default", uid=uid_filho)
    assert len(hist) == 1
    assert hist[0]["eap_id_de"] == "1.1"
    assert hist[0]["eap_id_para"] == "2.1"
    assert hist[0]["motivo"] == "reorganizacao de frentes"
    # neto tambem historico
    hneto = db.historico_movimentos(project_id="default", uid=uid_neto)
    assert hneto[0]["eap_id_de"] == "1.1.1"
    assert hneto[0]["eap_id_para"] == "2.1.1"


def test_move_ciclo_bloqueado(db):
    nos_de_teste(db)
    with pytest.raises(ValueError) as e:
        db.mover_nodo("1.1", "1.1.1", "default")
    assert "ciclo" in str(e.value).lower()


def test_buscar_por_uid_projeto_escopado(db):
    nos_de_teste(db)
    db.criar_projeto("P2")  # criar_projeto ja cria a raiz '1' (tipo projeto)
    uid_p2 = db.buscar_por_eap_id("1", "P2")["uid"]
    assert db.buscar_por_uid(uid_p2, "default") is None   # uid vive no P2
    assert db.buscar_por_uid(uid_p2, "P2")["project_id"] == "P2"
