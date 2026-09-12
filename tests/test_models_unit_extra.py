"""Testes de unidade complementares — fecham lacunas de cobertura da camada
de dados que não eram exercitadas por ``test_models_unit.py``/``test_corpus.py``
(as duas suítes que o gate de cobertura do CI roda). Cobrem: filtros de
template, caminhos de erro de validação/projeto, e algumas leituras simples
de ``nodes.py`` (buscar por uid, histórico, pacotes sem dono, por tipo de
frente, busca textual, deletar com/sem cascade).
"""
from __future__ import annotations

import pytest

from conftest import nos_de_teste


# ── validacao.py: caminhos de erro e casos de borda ────────────────────────

def test_normalizar_tipo_frente_instalacoes_depreciado(db):
    """'instalacoes' foi dividido em eletrica/hidrossanitaria — erro dedicado."""
    with pytest.raises(ValueError, match="DEPRECIADO"):
        db.normalizar_tipo_frente("instalacoes")


def test_normalizar_tipo_frente_none_e_vazio(db):
    assert db.normalizar_tipo_frente(None) is None
    assert db.normalizar_tipo_frente("") is None


def test_normalizar_unidade_none_e_vazia(db):
    assert db.normalizar_unidade(None) is None
    assert db.normalizar_unidade("") is None


def test_normalizar_nome_frase_none_e_stopword(db):
    assert db.normalizar_nome_frase(None) is None
    assert db.normalizar_nome_frase("") == ""
    # stopword no meio da frase permanece minúscula; sigla com número mantém caixa
    assert db.normalizar_nome_frase("VIGA DE CONCRETO CA-50") == "Viga de Concreto CA-50"


# ── templates.py: filtros combinados e contagem ────────────────────────────

def _template(**over):
    base = {
        "projeto_tipo": "casa", "area_m2_min": 50.0, "area_m2_max": 150.0,
        "metodo_construtivo": "alvenaria_estrutural", "regiao": "sul",
        "eap_node": "1.1", "nome": "Item", "unidade": "m2",
        "quantidade_media": 10.0, "desvio_padrao": 1.0,
        "produtividade": None, "fonte": "teste",
    }
    base.update(over)
    return base


def test_listar_templates_filtro_area_e_metodo(db):
    db.inserir_template(_template(nome="Dentro da faixa"))
    db.inserir_template(_template(nome="Fora da faixa", area_m2_min=200.0, area_m2_max=300.0))
    db.inserir_template(_template(nome="Outro metodo", metodo_construtivo="concreto_armado"))

    achados = db.listar_templates(area_m2=100.0, metodo_construtivo="alvenaria_estrutural")
    nomes = {t["nome"] for t in achados}
    assert nomes == {"Dentro da faixa"}


def test_listar_templates_paginacao_e_contagem_ignora_paginacao(db):
    for i in range(5):
        db.inserir_template(_template(nome=f"Item {i}", eap_node=f"1.{i}"))

    pagina = db.listar_templates(projeto_tipo="casa", limit=2, offset=0)
    assert len(pagina) == 2
    total = db.contar_templates_filtrados(projeto_tipo="casa")
    assert total == 5
    assert db.contar_templates() == 5


def test_contar_templates_filtrados_sem_match(db):
    db.inserir_template(_template())
    assert db.contar_templates_filtrados(projeto_tipo="galpao_industrial") == 0


# ── projetos.py: caminhos de erro ──────────────────────────────────────────

def test_criar_projeto_vazio_e_duplicado(db):
    with pytest.raises(ValueError, match="obrigatório"):
        db.criar_projeto("   ")
    db.criar_projeto("obra-x", nome="Obra X")
    with pytest.raises(ValueError, match="já existe"):
        db.criar_projeto("obra-x")


def test_atualizar_projeto_sem_campos_ou_inexistente(db):
    db.criar_projeto("obra-y", nome="Obra Y")
    with pytest.raises(ValueError, match="Nenhum campo válido"):
        db.atualizar_projeto("obra-y")
    with pytest.raises(ValueError, match="não existe"):
        db.atualizar_projeto("obra-fantasma", nome="X")
    atualizado = db.atualizar_projeto("obra-y", nome="Obra Y Renomeada")
    assert atualizado["nome"] == "Obra Y Renomeada"


def test_contar_projetos(db):
    assert db.contar_projetos() == 0
    db.criar_projeto("obra-1")
    db.criar_projeto("obra-2")
    assert db.contar_projetos() == 2


# ── nodes.py: leituras simples não exercitadas por test_models_unit ───────

def test_buscar_por_uid(db):
    nos_de_teste(db)
    no = db.buscar_por_eap_id("1.1.1")
    achado = db.buscar_por_uid(no["uid"])
    assert achado["eap_id"] == "1.1.1"
    assert db.buscar_por_uid("uid-que-nao-existe") is None
    assert db.buscar_por_uid("") is None


def test_listar_por_tipo_frente(db):
    nos_de_teste(db)
    fundacoes = db.listar_por_tipo_frente("fundacao")
    assert {n["eap_id"] for n in fundacoes} == {"1", "1.1", "1.1.1"}


def test_listar_pacotes_sem_dono(db):
    nos_de_teste(db)
    sem_dono = db.listar_pacotes_sem_dono()
    # 1.1.1 é a única folha da arvore base (1 e 1.1 tem filhos; 2 é folha tambem)
    ids = {n["eap_id"] for n in sem_dono}
    assert "1.1.1" in ids
    assert "2" in ids
    db.atualizar_nodo("1.1.1", {"responsavel": "Fulano", "project_id": "default"})
    sem_dono_depois = db.listar_pacotes_sem_dono()
    assert "1.1.1" not in {n["eap_id"] for n in sem_dono_depois}


def test_historico_movimentos_vazio_e_apos_mover(db):
    nos_de_teste(db)
    assert db.historico_movimentos() == []
    db.mover_nodo("1.1.1", "2", motivo="teste de historico")
    hist = db.historico_movimentos()
    assert len(hist) == 1
    assert hist[0]["eap_id_de"] == "1.1.1"
    # filtros
    assert len(db.historico_movimentos(eap_id_de="1.1.1")) == 1
    assert len(db.historico_movimentos(eap_id_de="inexistente")) == 0


def test_buscar_eap_node_por_varios_campos(db):
    nos_de_teste(db)
    db.atualizar_nodo("1.1.1", {"responsavel": "Maria Silva", "project_id": "default"})
    assert db.buscar_eap_node("") == []
    assert any(n["eap_id"] == "1.1.1" for n in db.buscar_eap_node("concreto"))
    assert any(n["eap_id"] == "1.1.1" for n in db.buscar_eap_node("Maria"))
    assert any(n["eap_id"] == "1" for n in db.buscar_eap_node("FR-001"))
    assert any(n["eap_id"] == "1" for n in db.buscar_eap_node("BL-A"))


def test_deletar_nodo_com_e_sem_cascade(db):
    nos_de_teste(db)
    with pytest.raises(ValueError, match="filho"):
        db.deletar_nodo("1.1")  # tem filho 1.1.1, sem cascade deve falhar
    resultado = db.deletar_nodo("1.1", cascade=True)
    assert resultado["deletado"] is True
    assert db.buscar_por_eap_id("1.1") is None
    assert db.buscar_por_eap_id("1.1.1") is None
    with pytest.raises(ValueError, match="não encontrado"):
        db.deletar_nodo("eap-id-fantasma")


def test_normalizar_nomes_projeto(db):
    nos_de_teste(db)
    db.atualizar_nodo("1.1.1", {"nome": "CONCRETO EM CAIXA ALTA", "project_id": "default"})
    alterados = db.normalizar_nomes_projeto("default")
    assert alterados >= 1
    assert db.buscar_por_eap_id("1.1.1")["nome"] == "Concreto Em Caixa Alta"
