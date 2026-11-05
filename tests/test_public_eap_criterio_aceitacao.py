"""Regressao da auditoria stateless do MCP EAP publico."""
from public_mcp import avaliar_evidencia_eap


def test_criterio_aceitacao_estruturado():
    item = {"responsavel": "QA", "criterio_aceitacao": "Inspecao aprovada", "quantidade": 10, "produtividade": 2, "fonte": "QA"}
    result = avaliar_evidencia_eap([item])
    assert result["cobertura"]["dicionario_minimo"]["preenchidos"] == 1
    assert result["lacunas"] == []
    assert result["persistido"] is False


def test_criterio_aceite_legado():
    result = avaliar_evidencia_eap([{"responsavel": "QA", "criterio_aceite": "Aceito"}])
    assert result["cobertura"]["dicionario_minimo"]["preenchidos"] == 1


def test_responsavel_obrigatorio():
    result = avaliar_evidencia_eap([{"criterio_aceitacao": "Aceito"}])
    assert result["cobertura"]["dicionario_minimo"]["preenchidos"] == 0
