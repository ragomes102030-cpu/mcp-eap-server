"""Skill de orquestracao da EAP - cria EAPs completas a partir de poucos parametros."""
from __future__ import annotations
from typing import Any
import models


def _nome_fase(fase_num: str) -> str:
    fases = {"1": "FUNDAÇÕES", "2": "ESTRUTURA", "3": "ALVENARIA", "4": "COBERTURA", "5": "INSTALAÇÕES", "6": "ACABAMENTO"}
    return fases.get(fase_num, f"FASE {fase_num}")


async def criar_eap_completa(project_id: str, tipo_obra: str, area_m2: float, metodo_construtivo: str | None = None, regiao: str | None = None, nome_projeto: str | None = None) -> dict[str, Any]:
    """Cria EAP inteira baseada em templates reais."""
    templates = models.listar_templates(tipo_obra, area_m2, metodo_construtivo)
    if not templates:
        return {"erro": f"Nenhum template para {tipo_obra} de {area_m2}m²"}
    if regiao:
        templates = [t for t in templates if t.get("regiao") == regiao] or templates
    fases: dict[str, list[dict]] = {}
    for t in templates:
        nivel1 = t["eap_node"].split(".")[0]
        fases.setdefault(nivel1, []).append(t)
    nos_criados = []
    raiz_nome = nome_projeto or f"{tipo_obra.upper()} {area_m2}m²"
    raiz = models.inserir_nodo({"eap_id": "1", "parent_id": None, "nivel": 1, "project_id": project_id, "frente_id": "", "local_id": None, "tipo_frente": tipo_obra, "nome": raiz_nome, "unidade": "conj", "quantidade": None})
    nos_criados.append(raiz)
    eap_id_fase = 2
    for fase_num in sorted(fases.keys()):
        fase_templates = fases[fase_num]
        primeiro = fase_templates[0]
        fase = models.inserir_nodo({"eap_id": str(eap_id_fase), "parent_id": "1", "nivel": 2, "project_id": project_id, "frente_id": "", "local_id": None, "tipo_frente": primeiro["tipo_frente"] if primeiro.get("tipo_frente") else tipo_obra, "nome": _nome_fase(fase_num), "unidade": "conj", "quantidade": None})
        nos_criados.append(fase)
        eap_id_item = 1
        for t in fase_templates:
            try:
                tipo_frente = t["tipo_frente"] if t.get("tipo_frente") else tipo_obra
                quantidade = t["quantidade_media"] if t.get("quantidade_media") else None
                models.inserir_nodo({"eap_id": f"{eap_id_fase}.{eap_id_item}", "parent_id": str(eap_id_fase), "nivel": 3, "project_id": project_id, "frente_id": "", "local_id": None, "tipo_frente": tipo_frente, "nome": t["nome"], "unidade": t["unidade"], "quantidade": quantidade})
                eap_id_item += 1
            except Exception:
                pass
        eap_id_fase += 1
    return {"project_id": project_id, "tipo_obra": tipo_obra, "area_m2": area_m2, "total_nos": len(nos_criados), "total_fases": len(fases)}


async def sugerir_eap(tipo_obra: str, area_m2: float, metodo_construtivo: str | None = None, regiao: str | None = None) -> dict[str, Any]:
    """Sugere estrutura de EAP sem persistir."""
    templates = models.listar_templates(tipo_obra, area_m2, metodo_construtivo)
    if not templates:
        return {"erro": f"Nenhum template para {tipo_obra}"}
    if regiao:
        templates = [t for t in templates if t.get("regiao") == regiao] or templates
    fases: dict[str, list[dict]] = {}
    for t in templates:
        nivel1 = t["eap_node"].split(".")[0]
        fases.setdefault(nivel1, []).append({"nome": t["nome"], "unidade": t["unidade"], "quantidade_sugerida": t.get("quantidade_media"), "produtividade": t.get("produtividade")})
    return {"tipo_obra": tipo_obra, "area_m2": area_m2, "total_fases": len(fases), "total_itens": sum(len(v) for v in fases.values()), "fases": {k: v for k, v in sorted(fases.items())}}


async def relatorio_eap(project_id: str) -> dict[str, Any]:
    """Resumo executivo da EAP de um projeto."""
    nos = models.listar_todos(project_id)
    if not nos:
        return {"erro": f"Projeto {project_id} vazio"}
    folhas = [n for n in nos if not models.listar_filhos(n["eap_id"])]
    com_qtd = [n for n in nos if n.get("quantidade")]
    tipos = {}
    for n in nos:
        tf = n.get("tipo_frente", "sem_tipo")
        tipos[tf] = tipos.get(tf, 0) + 1
    validacao = models.validar_estrutura()
    return {"project_id": project_id, "total_nos": len(nos), "nos_folha": len(folhas), "nos_com_quantidade": len(com_qtd), "por_tipo_frente": tipos, "validacao": validacao["resumo"], "problemas": validacao["problemas"]}


async def clonar_eap(project_id_origem: str, project_id_destino: str) -> dict[str, Any]:
    """Clona estrutura de EAP de um projeto pra outro."""
    nos_origem = models.listar_todos(project_id_origem)
    if not nos_origem:
        return {"erro": "Projeto origem vazio"}
    if models.listar_todos(project_id_destino):
        return {"erro": "Projeto destino ja tem dados"}
    mapeamento = {}
    for no in sorted(nos_origem, key=lambda n: n["nivel"]):
        eid_antigo = no["eap_id"]
        pai_antigo = no.get("parent_id")
        if pai_antigo is None:
            eid_novo = eid_antigo
        else:
            pai_novo = mapeamento.get(pai_antigo)
            if pai_novo is None:
                continue
            eid_novo = f"{pai_novo}.{eid_antigo.split(".")[-1]}"
        mapeamento[eid_antigo] = eid_novo
        models.inserir_nodo({"eap_id": eid_novo, "parent_id": mapeamento.get(pai_antigo), "nivel": no["nivel"], "project_id": project_id_destino, "frente_id": no.get("frente_id", ""), "local_id": no.get("local_id"), "tipo_frente": no.get("tipo_frente", ""), "nome": no["nome"], "unidade": no.get("unidade"), "quantidade": no.get("quantidade")})
    return {"project_id_origem": project_id_origem, "project_id_destino": project_id_destino, "total_nos_clonados": len(mapeamento)}


async def comparar_com_template(project_id: str, tipo_obra: str, area_m2: float, metodo_construtivo: str | None = None) -> dict[str, Any]:
    """Compara EAP real com template e aponta divergencias."""
    nos_projeto = models.listar_todos(project_id)
    templates = models.listar_templates(tipo_obra, area_m2, metodo_construtivo)
    if not templates:
        return {"erro": "Template nao encontrado"}
    nomes_projeto = {n["nome"].lower().strip() for n in nos_projeto if n.get("nome")}
    nomes_template = {t["nome"].lower().strip() for t in templates}
    presentes = nomes_template & nomes_projeto
    faltando = nomes_template - nomes_projeto
    extras = nomes_projeto - nomes_template
    return {"project_id": project_id, "tipo_obra": tipo_obra, "area_m2": area_m2, "itens_presentes": len(presentes), "itens_faltando": len(faltando), "itens_extras": len(extras), "faltando": sorted(faltando), "extras": sorted(extras), "cobertura_percentual": round(100 * len(presentes) / len(nomes_template)) if nomes_template else 0}
