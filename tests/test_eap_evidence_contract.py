from eap_evidence_contract import auditar_cobertura_evidencias


def test_missing_quantity_units_and_measurement_dictionary_are_reported_as_gaps():
    result = auditar_cobertura_evidencias([{
        "quantidade": 1,
        "produtividade": 1,
        "fonte": "TESTE-SINTETICO",
        "responsavel": "Equipe de teste",
        "criterio_aceitacao": "Inspecao de teste",
        "dicionario": {
            "descricao": "Servico sem unidade",
            "localizacao": "Torre A",
        },
    }])

    assert result["cobertura"]["dicionario_minimo"]["preenchidos"] == 0
    assert result["cobertura"]["unidade_quantidade"] == {"preenchidos": 0, "total": 1}
    assert result["cobertura"]["unidade_produtividade"] == {"preenchidos": 0, "total": 1}
    assert {"dicionario_minimo", "unidade_quantidade", "unidade_produtividade"} <= set(result["lacunas"])


def test_complete_dictionary_requires_code_unit_measurement_location_and_owner():
    result = auditar_cobertura_evidencias([{
        "quantidade": 10,
        "unidade": "m",
        "produtividade": 2,
        "unidade_produtividade": "m/dia",
        "fonte": ["FD639-EX-HID-014-R03"],
        "dicionario": {
            "codigo": "1.2.3",
            "descricao": "Tubulação sanitária",
            "unidade": "m",
            "criterio_medicao": "Comprimento instalado conforme projeto",
            "localizacao": "Torre A, 2º ao 3º pavimento",
            "disciplina": "hidrossanitário",
            "responsavel": "Equipe hidráulica",
            "criterio_aceitacao": "Inspeção e teste registrados",
        },
    }])

    assert result["cobertura"]["dicionario_minimo"] == {"preenchidos": 1, "total": 1}
    assert result["cobertura"]["unidade_quantidade"] == {"preenchidos": 1, "total": 1}
    assert result["cobertura"]["unidade_produtividade"] == {"preenchidos": 1, "total": 1}
    assert result["lacunas"] == []


def test_schema_publishes_unit_and_discipline_fields():
    from pydantic import TypeAdapter
    from eap_evidence_contract import DicionarioEapPublico, ItemEvidenciaEapPublica

    item = TypeAdapter(ItemEvidenciaEapPublica).json_schema()
    dictionary = TypeAdapter(DicionarioEapPublico).json_schema()

    assert {"unidade", "quantityUnit", "unidade_produtividade", "productivityUnit"} <= set(item["properties"])
    assert {"codigo", "code", "descricao", "description", "unidade", "unit",
            "criterio_medicao", "measurementCriterion", "localizacao", "location",
            "disciplina", "discipline", "responsavel", "responsible",
            "criterio_aceitacao", "acceptanceCriteria"} <= set(dictionary["properties"])


def test_pending_markers_do_not_count_as_filled_evidence():
    result = auditar_cobertura_evidencias([{
        "quantidade": 1,
        "unidade": "NAO_DECLARADA",
        "produtividade": 1,
        "unidade_produtividade": "PENDENTE",
        "fonte": "FD639-EX-HID-014-R03",
        "dicionario": {
            "codigo": "A DEFINIR",
            "descricao": "Serviço hidrossanitário",
            "unidade": "NAO_DECLARADA",
            "criterio_medicao": "A confirmar",
            "localizacao": "Torre A",
            "disciplina": "hidrossanitário",
            "responsavel": "Equipe hidráulica",
            "criterio_aceitacao": "PENDENTE",
        },
    }])

    assert result["cobertura"]["unidade_quantidade"] == {"preenchidos": 0, "total": 1}
    assert result["cobertura"]["unidade_produtividade"] == {"preenchidos": 0, "total": 1}
    assert result["cobertura"]["dicionario_minimo"] == {"preenchidos": 0, "total": 1}
    assert {"unidade_quantidade", "unidade_produtividade", "dicionario_minimo"} <= set(result["lacunas"])


def test_root_unit_owner_and_acceptance_fields_remain_valid_aliases():
    result = auditar_cobertura_evidencias([{
        "unidade": "m",
        "responsavel": "Equipe hidráulica",
        "criterio_aceitacao": "Teste registrado",
        "dicionario": {
            "codigo": "1.2.3",
            "descricao": "Tubulação sanitária",
            "criterio_medicao": "Comprimento instalado",
            "localizacao": "Torre A",
            "disciplina": "hidrossanitário",
        },
    }])

    assert result["cobertura"]["unidade_quantidade"] == {"preenchidos": 1, "total": 1}
    assert result["cobertura"]["dicionario_minimo"] == {"preenchidos": 1, "total": 1}


def test_english_dictionary_unit_alias_counts_as_quantity_unit():
    result = auditar_cobertura_evidencias([{
        "quantity": 8,
        "productivity": 4,
        "productivityUnit": "m/day",
        "source": "D-001 REV-A",
        "dictionary": {
            "code": "1.2.3",
            "description": "Sanitary pipe installation",
            "unit": "m",
            "measurementCriterion": "Installed length per drawing",
            "location": "Tower A, floors 2 to 3",
            "discipline": "plumbing",
            "responsible": "Plumbing crew",
            "acceptanceCriteria": "Inspection and test records",
        },
    }])

    assert result["cobertura"]["unidade_quantidade"] == {"preenchidos": 1, "total": 1}
    assert result["cobertura"]["dicionario_minimo"] == {"preenchidos": 1, "total": 1}
    assert result["lacunas"] == []


def test_each_incomplete_item_is_returned_with_a_traceable_reference():
    result = auditar_cobertura_evidencias([
        {
            "quantidade": 3,
            "unidade": "un",
            "produtividade": 1,
            "unidade_produtividade": "un/dia",
            "fonte": "FD639-EST-001-R02",
            "dicionario": {
                "codigo": "1.1.1",
                "descricao": "Estacas Torre A",
                "criterio_medicao": "Contagem por estaca executada",
                "localizacao": "Torre A",
                "disciplina": "estrutura",
                "responsavel": "Equipe de fundação",
                "criterio_aceitacao": "Relatório de execução aprovado",
            },
        },
        {
            "quantidade": 4,
            "fonte": "FD639-HID-018-R06::linha-14",
            "dicionario": {"codigo": "4.1.14", "localizacao": "Torre A, pavimento tipo"},
        },
    ])

    assert result["itens_com_lacunas"] == [{
        "indice": 2,
        "referencia": "4.1.14",
        "fonte": "FD639-HID-018-R06::linha-14",
        "lacunas": ["produtividade", "unidade_quantidade", "unidade_produtividade", "dicionario_minimo"],
    }]
