"""Testes de unidade da camada de dados (pacote models/) em banco temporario."""
from __future__ import annotations

import sqlite3

import pytest

from conftest import nos_de_teste


def test_normalizacao_unidade_e_tipo(db):
    assert db.normalizar_unidade("m2") == "m²"
    assert db.normalizar_unidade("M3") == "m³"
    assert db.normalizar_tipo_frente("Fundações") == "fundacao"
    assert db.normalizar_tipo_frente("alvenaria_estrutural") == "alvenaria"
    with pytest.raises(ValueError):
        db.normalizar_unidade("sacola")
    with pytest.raises(ValueError):
        db.normalizar_tipo_frente("terraplanagem")


def test_criar_nos_hierarquia_e_quantidade_em_folha(db):
    nos_de_teste(db)
    assert db.buscar_por_eap_id("1.1.1")["quantidade"] == 12.0
    # criar folha com quantidade e valido
    filho = db.inserir_nodo({"eap_id": "1.1.2", "parent_id": "1.1", "nivel": 3,
                             "frente_id": "FR-001", "local_id": "BL-A",
                             "tipo_frente": "fundacao", "nome": "Armacao",
                             "unidade": "kg", "quantidade": 300.0})
    assert filho["eap_id"] == "1.1.2"
    # quantidade em no com filhos rejeitada no update
    with pytest.raises(ValueError):
        db.atualizar_nodo("1.1", {"quantidade": 5.0, "project_id": "default"})


def test_proximo_eap_id(db):
    nos_de_teste(db)
    assert db.proximo_eap_id(None) == "3"  # raizes 1 e 2 existem
    assert db.proximo_eap_id("1.1") == "1.1.2"


def test_mover_renumera_e_bloqueia_ciclo(db):
    nos_de_teste(db)
    mov = db.mover_nodo("1.1", "2", "default")
    assert mov["movido"] is True
    assert mov["eap_id"] == "2.1"
    assert mov["nivel"] == 2
    assert db.buscar_por_eap_id("2.1.1", "default")["parent_id"] == "2.1"
    with pytest.raises(ValueError):
        db.mover_nodo("2", "2.1", "default")


def test_validar_avisos_semanticos(db):
    nos_de_teste(db)  # 2 raizes capitalizadas (sem avisos de CAIXA ALTA)
    db.inserir_nodo({"eap_id": "1.2", "parent_id": "1", "nivel": 2,
                     "frente_id": "FR-001", "local_id": "BL-A",
                     "tipo_frente": "estrutura", "nome": "Vigas estruturais",
                     "unidade": "conj", "quantidade": None})
    r = db.validar_estrutura("default")
    assert r["resumo"]["total_problemas"] == 0
    assert r["resumo"]["arvore_valida"] is True
    texto = "\n".join(r["avisos"])
    assert "raízes" in texto or "raizes" in texto
    assert "diverge do pai '1'" in texto


def test_validar_strict_multi_root(db):
    """F1.2: com strict (default de producao), multi-raiz e PROBLEMA, nao aviso."""
    nos_de_teste(db)  # arvore com 2 raizes (1 e 2)
    r = db.validar_estrutura("default", strict_single_root=True)
    assert r["resumo"]["total_problemas"] == 1
    assert r["resumo"]["arvore_valida"] is False
    assert any("MULTI_ROOT" in p for p in r["problemas"])
    # O ramo legado (aviso, strict desligado) continua disponivel.
    r2 = db.validar_estrutura("default", strict_single_root=False)
    assert r2["resumo"]["total_problemas"] == 0
    assert any("raízes" in a or "raizes" in a for a in r2["avisos"])


def test_validar_caixa_alta_e_agregador_com_unidade(db):
    db.inserir_nodo({"eap_id": "1", "parent_id": None, "nivel": 1,
                     "frente_id": "FR-A", "local_id": "L1",
                     "tipo_frente": "estrutura", "nome": "ESTRUTURA",
                     "unidade": "m³", "quantidade": None})
    db.inserir_nodo({"eap_id": "1.1", "parent_id": "1", "nivel": 2,
                     "frente_id": "FR-A", "local_id": "L1",
                     "tipo_frente": "estrutura", "nome": "Pilares",
                     "unidade": "conj", "quantidade": None})
    r = db.validar_estrutura("default")
    assert r["resumo"]["total_problemas"] == 0
    texto = "\n".join(r["avisos"])
    assert "CAIXA ALTA" in texto
    assert "carrega unidade de medida 'm³'" in texto


def test_validar_problemas_estruturais(db):
    nos_de_teste(db)
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("UPDATE eap_node SET parent_id = '999' WHERE eap_id = '1.1'")
    conn.commit()
    conn.close()
    r = db.validar_estrutura("default")
    assert r["resumo"]["total_problemas"] >= 1
    assert r["resumo"]["arvore_valida"] is False
    assert any("órfão" in p or "orfao" in p for p in r["problemas"])


def test_projeto_dao(db):
    p = db.criar_projeto("OBRA-1", nome="Residencial Teste", tipo_obra="casa",
                         area_m2=120.0, regiao="sudeste")
    assert p["project_id"] == "OBRA-1" and p["nome"] == "Residencial Teste"
    with pytest.raises(ValueError):
        db.criar_projeto("OBRA-1", nome="duplicado")
    up = db.atualizar_projeto("OBRA-1", area_m2=200.0, cliente="ACME")
    assert up["area_m2"] == 200.0 and up["cliente"] == "ACME"
    lista = {x["project_id"]: x for x in db.listar_projetos()}
    assert lista["OBRA-1"]["total_nos"] == 1  # raiz criada por criar_projeto
    raiz = db.buscar_por_eap_id("1", "OBRA-1")
    assert raiz is not None and raiz["tipo_frente"] == "projeto"
    assert raiz["nome"] == "Residencial Teste"
    db.inserir_nodo({"project_id": "OBRA-1", "eap_id": "1.1", "parent_id": "1",
                     "nivel": 2, "frente_id": "FR-A", "tipo_frente": "fundacao",
                     "nome": "Fundacoes", "unidade": None, "quantidade": None})
    lista2 = {x["project_id"]: x for x in db.listar_projetos()}
    assert lista2["OBRA-1"]["total_nos"] == 2
    delp = db.deletar_projeto("OBRA-1")
    assert delp["deletado"] is True and delp["total_nos"] == 2
    assert db.buscar_projeto("OBRA-1") is None


def test_isolamento_entre_projetos(db):
    nos_de_teste(db)  # default com '1' e '2'
    db.criar_projeto("P2")
    db.inserir_nodo({"project_id": "P2", "eap_id": "1.1", "parent_id": "1",
                     "nivel": 2, "frente_id": "FR-X", "tipo_frente": "fundacao",
                     "nome": "Fundacao dois", "unidade": None, "quantidade": None})
    assert db.buscar_por_eap_id("1", "default")["nome"] == "Fundacoes"
    assert db.buscar_por_eap_id("1", "P2")["nome"] == "P2"  # raiz automatica
    assert db.buscar_por_eap_id("1", "P2")["tipo_frente"] == "projeto"
    assert db.buscar_por_eap_id("1.1", "P2")["nome"] == "Fundacao dois"
    # sem projeto, a busca assume o default (nunca cruza projetos)
    assert db.buscar_por_eap_id("1")["project_id"] == "default"
    assert db.validar_estrutura("P2")["resumo"]["total_nos"] == 2
    assert db.validar_estrutura("default")["resumo"]["total_nos"] == 4
    assert [f["eap_id"] for f in db.listar_filhos("1", "P2")] == ["1.1"]


def test_auto_registro_projeto_ao_inserir(db):
    db.inserir_nodo({"project_id": "p-auto", "eap_id": "1", "parent_id": None,
                     "nivel": 1, "frente_id": "FR-A", "tipo_frente": "estrutura",
                     "nome": "Raiz", "unidade": "conj", "quantidade": None})
    assert db.buscar_projeto("p-auto") is not None
    ids = {p["project_id"] for p in db.listar_projetos()}
    assert "p-auto" in ids


def test_idempotencia_models(db):
    import sqlite3 as _sql

    db.salvar_idempotencia("req-1", "criar_eap_node", {"nome": "x"},
                           {"ok": True, "eap_id": "1"})
    assert db.verificar_idempotencia("req-1") == {"ok": True, "eap_id": "1"}
    assert db.verificar_idempotencia("req-nunca") is None
    # envelhece o registro para testar a limpeza de forma deterministica
    conn = _sql.connect(db.DB_PATH)
    conn.execute(
        "UPDATE eap_idempotency SET created_at = datetime('now', '-2 hours') "
        "WHERE request_id = 'req-1'"
    )
    conn.commit()
    conn.close()
    removidos = db.limpar_idempotencia_antiga(horas=1)
    assert removidos >= 1
    assert db.verificar_idempotencia("req-1") is None


def test_templates_filtro(db):
    db.inserir_template({"projeto_tipo": "casa", "area_m2_min": 80,
                         "area_m2_max": 150, "eap_node": "1.1",
                         "nome": "Escavacao sapatas", "unidade": "m³",
                         "quantidade_media": 48.5, "fonte": "teste"})
    db.inserir_template({"projeto_tipo": "apartamento", "area_m2_min": 60,
                         "area_m2_max": 120, "eap_node": "2.1",
                         "nome": "Laje pre-moldada", "unidade": "m²",
                         "quantidade_media": 80.0, "fonte": "teste"})
    assert len(db.listar_templates("casa")) == 1
    assert len(db.listar_templates()) == 2
    assert db.contar_templates() == 2


def test_montar_arvore_subarvore(db):
    nos_de_teste(db)
    arv = db.montar_arvore(None, "default")
    assert [r["eap_id"] for r in arv] == ["1", "2"]
    sub = db.montar_arvore("1", "default")
    assert sub[0]["eap_id"] == "1"
    assert [f["eap_id"] for f in sub[0]["filhos"]] == ["1.1"]
    with pytest.raises(ValueError):
        db.montar_arvore("9.9", "default")

