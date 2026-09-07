"""F1.2 - MULTI_ROOT com flag de transicao (strict_single_root)."""
from __future__ import annotations

from conftest import nos_de_teste


def test_multiraiz_sem_strict_segue_como_aviso(db):
    nos_de_teste(db)  # 2 raizes
    r = db.validar_estrutura("default", strict_single_root=False)
    assert r["resumo"]["total_problemas"] == 0
    assert r["resumo"]["arvore_valida"] is True
    texto = "\n".join(r["avisos"])
    assert "MULTI_ROOT" in texto or "raízes" in texto or "raizes" in texto


def test_multiraiz_com_strict_vira_erro(db):
    nos_de_teste(db)  # 2 raizes
    r = db.validar_estrutura("default", strict_single_root=True)
    assert r["resumo"]["total_problemas"] >= 1
    assert r["resumo"]["arvore_valida"] is False
    assert any("MULTI_ROOT" in p for p in r["problemas"])
    # nao duplica como aviso quando ja e erro
    assert not any("MULTI_ROOT" in a for a in r["avisos"])


def test_raiz_unica_com_strict_passa(db):
    # arvore canonica: 1 raiz (a obra)
    db.inserir_nodo({"eap_id": "1", "parent_id": None, "nivel": 1,
                     "frente_id": "FR-P", "tipo_frente": "projeto",
                     "nome": "Piemarta", "unidade": None, "quantidade": None})
    db.inserir_nodo({"eap_id": "1.1", "parent_id": "1", "nivel": 2,
                     "frente_id": "FR-001", "tipo_frente": "fundacao",
                     "nome": "Fundacoes", "unidade": None, "quantidade": None})
    db.inserir_nodo({"eap_id": "1.1.1", "parent_id": "1.1", "nivel": 3,
                     "frente_id": "FR-001", "tipo_frente": "fundacao",
                     "nome": "Escavacao", "unidade": "m³", "quantidade": 50.0})
    r = db.validar_estrutura("default", strict_single_root=True)
    assert r["resumo"]["total_problemas"] == 0
    assert r["resumo"]["arvore_valida"] is True
