"""Motor de proposta EAP para agentes: prompt + entregas estruturadas, sem LLM no servidor.

O cliente de IA interpreta o prompt e informa entregas. O motor valida, cria
codigos deterministas e entrega um rascunho versionado, sem persistencia.
"""
from __future__ import annotations
from typing import Any
from arquimedes_eap_contract import audit_contract, from_platform_payload

def propor_eap(prompt: str, entregas: list[dict[str, Any]], *,
               project_ref: str = "rascunho", version_ref: str = "proposta-1") -> dict[str, Any]:
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 12000:
        raise ValueError("Prompt obrigatorio, ate 12000 caracteres")
    if not isinstance(entregas, list) or not (1 <= len(entregas) <= 60):
        raise ValueError("Informe de 1 a 60 entregas interpretadas pelo agente")
    if not isinstance(project_ref, str) or not project_ref.strip() or not isinstance(version_ref, str) or not version_ref.strip():
        raise ValueError("Projeto e versao devem ser identificados")
    nodes = [{"code": "1", "parentCode": None, "name": "Escopo da obra", "nodeType": "grupo", "level": 1}]
    for index, entrega in enumerate(entregas, 1):
        if not isinstance(entrega, dict):
            raise ValueError("Entrega deve ser objeto")
        nome = entrega.get("nome")
        if not isinstance(nome, str) or not nome.strip() or len(nome) > 180:
            raise ValueError(f"Entrega {index}: nome obrigatorio")
        pacotes = entrega.get("pacotes")
        if not isinstance(pacotes, list) or not (1 <= len(pacotes) <= 30):
            raise ValueError(f"Entrega {index}: informe de 1 a 30 pacotes")
        group_code = f"1.{index}"
        nodes.append({"code": group_code, "parentCode": "1", "name": nome.strip(),
                      "nodeType": "grupo", "level": 2, "decompositionBasis": "deliverable"})
        for pos, pacote in enumerate(pacotes, 1):
            if not isinstance(pacote, dict):
                raise ValueError("Pacote deve ser objeto")
            label = pacote.get("nome")
            if not isinstance(label, str) or not label.strip() or len(label) > 180:
                raise ValueError(f"Pacote {group_code}.{pos}: nome obrigatorio")
            code = f"{group_code}.{pos}"
            node = {"code": code, "parentCode": group_code, "name": label.strip(),
                    "nodeType": "pacote", "level": 3, "decompositionBasis": "component"}
            for source, dest in (("descricao", "description"), ("inclusoes", "inclusions"),
                                 ("exclusoes", "exclusions"), ("responsavel", "responsible"),
                                 ("criterio_aceite", "acceptanceCriteria"),
                                 ("local", "location"), ("unidade", "unit"),
                                 ("quantidade", "plannedQuantity")):
                if source in pacote and pacote[source] is not None:
                    node[dest] = pacote[source]
            nodes.append(node)
    if len(nodes) > 150:
        raise ValueError("Proposta excede limite de 150 nos")
    payload = {"projectRef": project_ref.strip(), "versionRef": version_ref.strip(), "nodes": nodes}
    result = audit_contract(from_platform_payload(payload))
    return {"ok": result.structural_valid, "contrato": "arquimedes.eap.v1",
            "proposta": payload, "avisos": [i.__dict__ for i in result.issues],
            "regra_100_verificada": result.scope_coverage_verified,
            "persistido": False, "origem": "interpretacao_do_agente_sobre_prompt",
            "observacao": "Entregas e pacotes sao fornecidos pelo agente; motor nao gera escopo por LLM nem inventa quantitativos. Revisao humana necessaria."}
