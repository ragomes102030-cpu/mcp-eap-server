"""Teste das regras de parentesco imediato sem banco."""
from public_mcp import validar_estrutura_eap


def test_rejeita_pai_ancestral_sem_nivel_intermediario():
    nos = [
        {"eap_id": "1", "parent_id": None, "nivel": 1},
        {"eap_id": "1.1", "parent_id": "1", "nivel": 2},
        {"eap_id": "1.1.1", "parent_id": "1", "nivel": 3},
    ]
    resultado = validar_estrutura_eap(nos)
    assert resultado["ok"] is False
    assert any("pai imediato 1.1" in erro for erro in resultado["erros"])
    assert resultado["persistido"] is False


def test_aceita_pai_imediato_e_sem_banco():
    nos = [
        {"eap_id": "1", "parent_id": None, "nivel": 1},
        {"eap_id": "1.1", "parent_id": "1", "nivel": 2},
        {"eap_id": "1.1.1", "parent_id": "1.1", "nivel": 3},
    ]
    resultado = validar_estrutura_eap(nos)
    assert resultado["ok"] is True
    assert resultado["erros"] == []
    assert resultado["total_nos"] == 3
