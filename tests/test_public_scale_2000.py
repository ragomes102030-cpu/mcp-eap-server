"""Limites de escala públicos sem banco, redes ou escrita de projetos."""
import pytest

from public_mcp import avaliar_evidencia_eap, validar_estrutura_eap
from eap_prompt_assistant import propor_eap


def arvore(qtd):
    assert qtd >= 2
    return [
        {"eap_id": "1", "parent_id": None, "nivel": 1},
        {"eap_id": "1.1", "parent_id": "1", "nivel": 2},
        *[
            {"eap_id": f"1.1.{i}", "parent_id": "1.1", "nivel": 3}
            for i in range(1, qtd - 1)
        ],
    ]


def test_audita_2000_nos_em_memoria():
    r = validar_estrutura_eap(arvore(2000))
    assert r["ok"] is True
    assert r["total_nos"] == 2000
    assert r["erros"] == []
    assert r["persistido"] is False


def test_rejeita_2001_nos_sem_persistir():
    with pytest.raises(ValueError, match="2000"):
        validar_estrutura_eap(arvore(2001))


def test_evidencia_2000_pacotes_incompletos_sem_inventar_fontes():
    itens = [
        {"quantidade": 1, "produtividade": 2, "fonte": "",
         "responsavel": "", "criterio_aceitacao": ""}
        for _ in range(2000)
    ]
    r = avaliar_evidencia_eap(itens)
    assert r["total"] == 2000
    assert r["cobertura"]["quantidade"]["preenchidos"] == 2000
    assert r["cobertura"]["fonte"]["preenchidos"] == 0
    assert "fonte" in r["lacunas"]
    assert r["persistido"] is False


def proposta(n_entregas, n_pacotes):
    entregas = [
        {"nome": f"Fase {i}", "pacotes": [
            {"nome": f"Servico {i}.{j}", "quantidade": 2, "unidade": "m2"}
            for j in range(n_pacotes)
        ]}
        for i in range(n_entregas)
    ]
    return propor_eap("QA de obra multifamiliar, sem escopo inventado", entregas)


def test_proposta_1961_nos():
    r = proposta(70, 27)
    assert r["ok"] is True
    assert len(r["proposta"]["nodes"]) == 1961
    assert r["persistido"] is False
    assert r["regra_100_verificada"] is False


def test_proposta_2031_nos_rejeitada():
    with pytest.raises(ValueError, match="limite de 2000"):
        proposta(70, 28)


def test_conserva_limite_30_pacotes_por_entrega():
    with pytest.raises(ValueError, match="1 a 30 pacotes"):
        proposta(1, 31)
