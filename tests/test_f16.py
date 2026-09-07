"""F1.6 - retrabalho tipado (irmao R{n}, origem_uid, sem duplicidade)."""
from __future__ import annotations

import pytest


def _projeto_base(db, pid: str = "OBRA") -> str:
    db.criar_projeto(pid, nome="Obra Teste", tipo_obra="casa", area_m2=80.0)
    # NOTA: criar_projeto ya genera la raíz [1] (nivel 1, tipo 'projeto').
    db.inserir_nodo({"project_id": pid, "eap_id": "1.1", "parent_id": "1",
                     "nivel": 2, "frente_id": "FR-A", "tipo_frente": "estrutura",
                     "nome": "Estrutura", "unidade": None, "quantidade": None})
    db.inserir_nodo({"project_id": pid, "eap_id": "1.1.1", "parent_id": "1.1",
                     "nivel": 3, "frente_id": "FR-A", "tipo_frente": "estrutura",
                     "nome": "Concreto pilares", "unidade": "m³",
                     "quantidade": 12.0, "status": "concluido"})
    db.inserir_nodo({"project_id": pid, "eap_id": "1.1.2", "parent_id": "1.1",
                     "nivel": 3, "frente_id": "FR-A", "tipo_frente": "estrutura",
                     "nome": "Formas dos pilares", "unidade": "m²",
                     "quantidade": 40.0, "status": "concluido"})
    return pid


def test_registrar_retrabalho_cria_irmao_r1(db):
    pid = _projeto_base(db)
    orig = db.buscar_por_eap_id("1.1.1", pid)
    r = db.registrar_retrabalho(eap_id="1.1.1", project_id=pid,
                                motivo="infiltração em reboco")
    assert r["status"] == "retrabalho"
    assert r["revisao"] == 1
    assert r["origem_uid"] == orig["uid"]
    assert r["parent_id"] == "1.1"          # irmao do original
    assert r["nome"].startswith("R1")
    assert r["quantidade"] == 12.0          # herda qtd (custo do retrabalho)
    # original intacto
    orig2 = db.buscar_por_eap_id("1.1.1", pid)
    assert orig2["quantidade"] == 12.0 and orig2["status"] == "concluido"
    # R2 apos segundo retrabalho
    r2 = db.registrar_retrabalho(uid=orig["uid"], project_id=pid,
                                 motivo="nova não conformidade")
    assert r2["revisao"] == 2


def test_validar_nao_conta_duplicidade(db):
    pid = _projeto_base(db)
    db.registrar_retrabalho(eap_id="1.1.1", project_id=pid, motivo="reboco refeito")
    res = db.validar_estrutura(pid)
    assert res["resumo"]["total_problemas"] == 0
    assert res["resumo"]["arvore_valida"] is True
    # R nao e tratado como duplicidade (nenhum problema de duplicidade)
    assert not any("duplicid" in p.lower() for p in res["problemas"])


def test_resumo_breakdown_previsto_x_retrabalho(db):
    pid = _projeto_base(db)
    db.registrar_retrabalho(eap_id="1.1.1", project_id=pid,
                            motivo="infiltração em reboco")
    grupos = db.resumo_quantitativos(pid)
    m3 = {g["unidade"]: g for g in grupos
          if g["tipo_frente"] == "estrutura"}["m³"]
    assert m3["previsto"] == 12.0
    assert m3["retrabalho"] == 12.0
    assert m3["soma"] == 24.0


def test_motivo_obrigatorio_e_raiz_bloqueada(db):
    pid = _projeto_base(db)
    with pytest.raises(ValueError):
        db.registrar_retrabalho(eap_id="1.1.1", project_id=pid, motivo=None)
    with pytest.raises(ValueError):
        db.registrar_retrabalho(eap_id="1", project_id=pid, motivo="raiz?")
