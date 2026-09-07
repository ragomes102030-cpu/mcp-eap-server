"""F1.4 - folha mensuravel / N-A / FANTASMA + normalizacao de nomes."""
from __future__ import annotations


def _cria_projeto_sujo(db, pid: str = "DIRTA") -> None:
    """Projeto unico com folhas 'fantasma' (sem qtd) e nomes em CAIXA ALTA."""
    db.criar_projeto(pid, nome="CASITA 50M2", tipo_obra="casa", area_m2=50.0)
    db.inserir_nodo({"project_id": pid, "eap_id": "1.1", "parent_id": "1",
                     "nivel": 2, "frente_id": "FR-A", "local_id": "TERREO-GERAL",
                     "tipo_frente": "fundacao", "nome": "FUNDAÇÕES",
                     "unidade": None, "quantidade": None})
    db.inserir_nodo({"project_id": pid, "eap_id": "1.1.1", "parent_id": "1.1",
                     "nivel": 3, "frente_id": "FR-A", "local_id": "TERREO-GERAL",
                     "tipo_frente": "fundacao", "nome": "LIMPEZA DO TERRENO",
                     "unidade": "m²", "quantidade": None})
    db.inserir_nodo({"project_id": pid, "eap_id": "1.1.2", "parent_id": "1.1",
                     "nivel": 3, "frente_id": "FR-A", "local_id": "TERREO-GERAL",
                     "tipo_frente": "fundacao", "nome": "ESCAVAÇÃO DE VALAS",
                     "unidade": "m³", "quantidade": None})
    db.inserir_nodo({"project_id": pid, "eap_id": "1.1.3", "parent_id": "1.1",
                     "nivel": 3, "frente_id": "FR-A", "local_id": "TERREO-GERAL",
                     "tipo_frente": "fundacao", "nome": "Verba de imprevistos",
                     "unidade": None, "quantidade": None,
                     "nao_aplicavel": True, "motivo_na": "verba"})


def test_fantasma_em_folhas_sem_quantidade(db):
    _cria_projeto_sujo(db)
    r = db.validar_estrutura("DIRTA")
    fantasma = [a for a in r["avisos"] if "FANTASMA" in a]
    # 1.1.1 e 1.1.2 sao fantasma; 1.1.3 e N/A (nao conta)
    assert len(fantasma) == 2
    assert any("'1.1.1'" in a for a in fantasma)
    assert not any("'1.1.3'" in a for a in fantasma)


def test_preencher_quantidade_remove_fantasma(db):
    _cria_projeto_sujo(db)
    db.atualizar_nodo("1.1.1", {"project_id": "DIRTA", "quantidade": 50.0})
    r = db.validar_estrutura("DIRTA")
    fantasma = [a for a in r["avisos"] if "FANTASMA" in a]
    assert len(fantasma) == 1
    assert any("'1.1.2'" in a for a in fantasma)


def test_marcar_nao_aplicavel_remove_fantasma(db):
    _cria_projeto_sujo(db)
    db.atualizar_nodo("1.1.2", {"project_id": "DIRTA", "nao_aplicavel": True,
                                "motivo_na": "provisorio"})
    r = db.validar_estrutura("DIRTA")
    fantasma = [a for a in r["avisos"] if "FANTASMA" in a]
    assert len(fantasma) == 1
    assert any("'1.1.1'" in a for a in fantasma)


def test_normalizar_nomes_frase(db):
    assert db.normalizar_nome_frase("ESCAVAÇÃO SAPATAS") == "Escavação Sapatas"
    assert db.normalizar_nome_frase("AÇO CA-50") == "Aço CA-50"
    assert db.normalizar_nome_frase("CONCRETO VIGAS BALDRAME") == "Concreto Vigas Baldrame"

    _cria_projeto_sujo(db)
    alterados = db.normalizar_nomes_projeto("DIRTA")
    assert alterados >= 3  # raiz/fase/folhas em CAIXA ALTA
    r = db.validar_estrutura("DIRTA")
    caixa = [a for a in r["avisos"] if "CAIXA ALTA" in a]
    assert not caixa, caixa
