"""Regressao da auditoria stateless do MCP EAP publico."""
from public_mcp import avaliar_evidencia_eap


def test_criterio_aceitacao_estruturado():
    item = {
        "quantidade": 10, "unidade": "m", "produtividade": 2,
        "unidade_produtividade": "m/dia", "fonte": "QA",
        "dicionario": {
            "codigo": "1.2.3", "descricao": "Serviço de teste", "unidade": "m",
            "criterio_medicao": "Comprimento instalado", "localizacao": "Torre A",
            "disciplina": "estrutura", "responsavel": "QA",
            "criterio_aceitacao": "Inspecao aprovada",
        },
    }
    result = avaliar_evidencia_eap([item])
    assert result["cobertura"]["dicionario_minimo"]["preenchidos"] == 1
    assert result["lacunas"] == []
    assert result["persistido"] is False


def test_criterio_aceite_legado():
    result = avaliar_evidencia_eap([{"responsavel": "QA", "criterio_aceite": "Aceito"}])
    assert result["cobertura"]["dicionario_minimo"]["preenchidos"] == 0
    assert "dicionario_minimo" in result["lacunas"]


def test_responsavel_obrigatorio():
    result = avaliar_evidencia_eap([{"criterio_aceitacao": "Aceito"}])
    assert result["cobertura"]["dicionario_minimo"]["preenchidos"] == 0

def test_public_tool_schema_documents_evidence_fields():
    import asyncio
    import json
    from public_mcp import public_mcp

    tools = asyncio.run(public_mcp.list_tools())
    evaluator = next(tool for tool in tools if tool.name == "avaliar_evidencia_eap")
    schema = evaluator.input_schema
    item_schema = schema["properties"]["itens"]["items"]
    if "$ref" in item_schema:
        item_schema = schema["$defs"][item_schema["$ref"].rsplit("/", 1)[-1]]
    properties = item_schema["properties"]
    assert {"quantidade", "plannedQuantity", "produtividade", "productivity", "fonte", "source",
            "unidade", "quantityUnit", "unidade_produtividade", "productivityUnit",
            "responsavel", "responsible", "criterio_aceitacao", "acceptanceCriteria", "dicionario"} <= set(properties)
    assert item_schema.get("additionalProperties") is False
    dictionary_schema = properties["dicionario"]
    if "$ref" not in dictionary_schema:
        dictionary_schema = next(part for part in dictionary_schema.get("anyOf", []) if "$ref" in part)
    dictionary_schema = schema["$defs"][dictionary_schema["$ref"].rsplit("/", 1)[-1]]
    assert {"codigo", "descricao", "unidade", "criterio_medicao", "localizacao",
            "disciplina", "responsavel", "criterio_aceitacao", "discipline"} <= set(dictionary_schema["properties"])

    result = asyncio.run(public_mcp.call_tool("avaliar_evidencia_eap", {"itens": [{
        "plannedQuantity": 12,
        "quantityUnit": "m",
        "productivity": 3,
        "productivityUnit": "m/dia",
        "source": ["FD639-EX-HID-014-R03"],
        "dictionary": {"code": "1.2.3", "description": "Instalação sanitária",
                       "unit": "m", "measurementCriterion": "Comprimento instalado",
                       "location": "Torre A", "discipline": "hidrossanitário",
                       "responsible": "Equipe de instalações",
                       "acceptanceCriteria": "Ensaio aprovado"},
    }]}))
    assert not result.is_error
    audited = json.loads(result.content[0].text)
    assert audited["lacunas"] == [], audited
    assert audited["persistido"] is False


def test_aliases_and_nested_dictionary_are_audited_without_persistence():
    from eap_evidence_contract import auditar_cobertura_evidencias

    result = auditar_cobertura_evidencias([{
        "plannedQuantity": 12,
        "quantityUnit": "m",
        "productivity": 3,
        "productivityUnit": "m/dia",
        "source": ["FD639-EX-HID-014-R03"],
        "dictionary": {
            "code": "1.2.3",
            "description": "Instalação sanitária por pavimento",
            "unit": "m",
            "measurementCriterion": "Medição por comprimento instalado e testado",
            "location": "Torre A, 2º ao 3º pavimento",
            "discipline": "hidrossanitário",
            "responsible": "Equipe de instalações",
            "acceptanceCriteria": "Ensaio aprovado e registro de inspeção",
            "source": ["FD639-EX-HID-014-PLA_T2A-R03"],
        },
    }])
    assert result["cobertura"]["quantidade"]["preenchidos"] == 1
    assert result["cobertura"]["produtividade"]["preenchidos"] == 1
    assert result["cobertura"]["fonte"]["preenchidos"] == 1
    assert result["cobertura"]["dicionario_minimo"]["preenchidos"] == 1
    assert result["lacunas"] == []


def test_boolean_is_not_a_quantity_or_productivity():
    import asyncio

    import pytest
    from mcp.server.mcpserver.exceptions import ToolError
    from public_mcp import public_mcp
    from eap_evidence_contract import auditar_cobertura_evidencias

    result = auditar_cobertura_evidencias([{"quantidade": True, "produtividade": False}])
    assert result["cobertura"]["quantidade"]["preenchidos"] == 0
    assert result["cobertura"]["produtividade"]["preenchidos"] == 0
    with pytest.raises(ToolError, match="valid number"):
        asyncio.run(public_mcp.call_tool("avaliar_evidencia_eap", {
            "itens": [{"quantidade": True, "produtividade": False}],
        }))

def test_blank_root_fields_do_not_hide_nested_dictionary_evidence():
    from eap_evidence_contract import auditar_cobertura_evidencias

    result = auditar_cobertura_evidencias([{
        "fonte": "   ",
        "responsavel": "   ",
        "criterio_aceitacao": "   ",
        "dicionario": {
            "code": "1.2.3",
            "description": "Tubulação sanitária",
            "unit": "m",
            "measurementCriterion": "Comprimento instalado",
            "location": "Torre A",
            "discipline": "hidrossanitário",
            "source": ["FD639-EX-HID-014-PLA_T2A-R03"],
            "responsible": "Equipe hidráulica",
            "acceptanceCriteria": "Teste de estanqueidade registrado",
        },
    }])
    assert result["cobertura"]["fonte"]["preenchidos"] == 1
    assert result["cobertura"]["dicionario_minimo"]["preenchidos"] == 1


def test_empty_list_does_not_report_false_complete_coverage():
    from eap_evidence_contract import auditar_cobertura_evidencias

    result = auditar_cobertura_evidencias([])
    assert result["total"] == 0
    assert result["lacunas"] == ["quantidade", "produtividade", "unidade_quantidade",
                                  "unidade_produtividade", "fonte", "dicionario_minimo"]
