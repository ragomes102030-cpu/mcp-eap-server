"""F1.5 - matriz unidade pai-filho, FILHO_UNICO e resumo_quantitativos."""
from __future__ import annotations


def _monta_projeto(db, pid: str = "RESU") -> None:
    db.criar_projeto(pid, nome="Residencial Teste", tipo_obra="casa", area_m2=100.0)
    # fase com unidade 'conj' e folhas m3 -> UNIDADE_INCOMPATIVEL
    db.inserir_nodo({"project_id": pid, "eap_id": "1.1", "parent_id": "1",
                     "nivel": 2, "frente_id": "FR-A", "tipo_frente": "fundacao",
                     "nome": "Fundações", "unidade": "conj", "quantidade": None})
    for eap, nome, unid, qtd in (
        ("1.1.1", "Escavação de sapatas", "m³", 1280.0),
        ("1.1.2", "Concreto das sapatas", "m³", 240.0),
        ("1.1.3", "Impermeabilizante", "m²", None),  # null -> ignorado no soma
    ):
        db.inserir_nodo({"project_id": pid, "eap_id": eap, "parent_id": "1.1",
                         "nivel": 3, "frente_id": "FR-A", "tipo_frente": "fundacao",
                         "nome": nome, "unidade": unid, "quantidade": qtd})
    # fase estrutural coerente (sem unidade no agregador)
    db.inserir_nodo({"project_id": pid, "eap_id": "1.2", "parent_id": "1",
                     "nivel": 2, "frente_id": "FR-B", "tipo_frente": "estrutura",
                     "nome": "Estrutura", "unidade": None, "quantidade": None})
    for eap, nome, unid, qtd in (
        ("1.2.1", "Aço da estrutura", "kg", 150.0),
        ("1.2.2", "Concreto dos pilares", "m³", 8.0),
    ):
        db.inserir_nodo({"project_id": pid, "eap_id": eap, "parent_id": "1.2",
                         "nivel": 3, "frente_id": "FR-B", "tipo_frente": "estrutura",
                         "nome": nome, "unidade": unid, "quantidade": qtd})
    # fase com 1 unico filho -> FILHO_UNICO
    db.inserir_nodo({"project_id": pid, "eap_id": "1.3", "parent_id": "1",
                     "nivel": 2, "frente_id": "FR-C", "tipo_frente": "alvenaria",
                     "nome": "Alvenaria", "unidade": None, "quantidade": None})
    db.inserir_nodo({"project_id": pid, "eap_id": "1.3.1", "parent_id": "1.3",
                     "nivel": 3, "frente_id": "FR-C", "tipo_frente": "alvenaria",
                     "nome": "Blocos cerâmicos", "unidade": "m²", "quantidade": 135.0})


def test_unidade_incompativel_e_filho_unico(db):
    _monta_projeto(db)
    r = db.validar_estrutura("RESU")
    incompat = [a for a in r["avisos"] if "UNIDADE_INCOMPATIVEL" in a]
    assert incompat  # 1.1 'conj' com folhas m3
    assert any("'1.1'" in a for a in incompat)
    filho = [a for a in r["avisos"] if "FILHO_UNICO" in a]
    assert any("'1.3'" in a for a in filho)


def test_resumo_quantitativos_sem_misturar_unidades(db):
    _monta_projeto(db)
    grupos = db.resumo_quantitativos("RESU")
    mapa = {(g["tipo_frente"], g["unidade"]): g for g in grupos}
    # fundacao/m3 soma 1280+240 = 1520 (null e m2 ficam fora da soma)
    assert mapa[("fundacao", "m³")]["soma"] == 1520.0
    assert mapa[("estrutura", "kg")]["soma"] == 150.0
    assert mapa[("estrutura", "m³")]["soma"] == 8.0
    # null ignorado: grupo m² da fundacao tem soma 0 (mas folha conta)
    assert mapa[("fundacao", "m²")]["soma"] == 0.0
    assert mapa[("fundacao", "m²")]["folhas"] == 1
    # filtro por tipo
    so_fund = db.resumo_quantitativos("RESU", tipo_frente="fundacao")
    assert {g["tipo_frente"] for g in so_fund} == {"fundacao"}
