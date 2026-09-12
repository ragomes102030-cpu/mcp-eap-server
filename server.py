"""Servidor MCP (Model Context Protocol) de EAP para obras de construcao civil.

Versao HTTP/streamable para deploy em nuvem (Render, Railway, Fly.io).

Ferramentas expostas (18 tools):
  * criar_eap_node         cria no, gera EAP_ID hierarquico e calcula NIVEL
  * get_eap_tree           retorna a arvore em JSON aninhado
  * get_eap_node           retorna um no especifico
  * atualizar_eap_node     atualiza campos de um no existente
  * deletar_eap_node       deleta um no (com cascade opcional)
  * mover_eap_node         move um no (e subarvore) para outro pai, reenumerando
  * deletar_projeto        deleta todos os nos de um projeto
  * listar_projetos        lista projetos com contagem de nos
  * criar_projeto          cria um novo projeto (obra) com metadados
  * atualizar_projeto      atualiza metadados de um projeto (obra)
  * definir_criterio       define dicionario do pacote e dono/OBS (responsavel)
  * pacotes_sem_dono       lista pacotes (folhas) sem responsavel
  * resumo_quantitativos   quantitativos por (tipo_frente, unidade), so folhas
  * registrar_retrabalho   cria irmao R{n} de retrabalho (origem linkada)
  * validar_estrutura      detecta orfaos, duplicidades e NIVEL inconsistente
  * listar_por_tipo_frente filtra nos por tipo de frente de servico
  * buscar_eap_node        busca nos por termo (acento e caixa ignorados)
  * listar_templates       lista exemplos reais de EAP (templates)

Variaveis de ambiente:
  * PORT — porta TCP (padrao 10000). O Render injeta automaticamente.
  * TURSO_URL — URL do banco Turso (libSQL). Se vazio, usa sqlite3 local.
  * TURSO_TOKEN — token de autenticacao do Turso.
"""

from __future__ import annotations

import os
import sys
from typing import Annotated, Any, Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings
from pydantic import Field

import models
import schemas
from observability import log_tool_call

mcp = FastMCP(
    name="eap-server",
    instructions=(
        "Servidor MCP de Estrutura Analitica do Projeto (EAP) de obras. "
        "Gerencia nos hierarquicos (EAP_ID no formato '1.2.3') com PARENT_ID, "
        "NIVEL, PROJECT_ID, FRENTE_ID, LOCAL_ID, TIPO_FRENTE, NOME, UNIDADE e QUANTIDADE. "
        "Use criar_eap_node para inserir, get_eap_tree para navegar, "
        "get_eap_node para detalhe, atualizar_eap_node para atualizar, "
        "deletar_eap_node para remover, mover_eap_node para reorganizar a arvore, "
        "validar_estrutura para auditoria."
    ),
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


def _seguro(fn: Callable[[], Any], tool_name: str = "tool", **contexto: Any) -> dict[str, Any]:
    """Executa fn, loga a chamada (início/fim/erro) e converte qualquer
    excecao em resposta de erro.

    ``tool_name`` e ``contexto`` (ex.: project_id, eap_id) alimentam o log
    estruturado em ``observability.log_tool_call`` — nunca inclua payloads
    completos de entrada aqui, só identificadores.
    """
    try:
        with log_tool_call(tool_name, **contexto):
            return fn()
    except Exception as exc:
        return schemas.ErroOutput(erro=str(exc)).model_dump()


def _idempotente(
    request_id: str | None,
    tool_name: str,
    payload: Any,
    fn: Callable[[], Any],
    **contexto: Any,
) -> dict[str, Any]:
    """Executa ``fn`` com idempotência: se ``request_id`` já processado,
    devolve a resposta cacheada; senão, executa, salva e devolve.

    ``payload`` é o dict serializável (cache do pedido) e ``fn`` o corpo real
    da execução da tool (que retorna o dict de saída). A chamada é logada de
    forma estruturada (ver ``_seguro``), incluindo se veio do cache.
    """
    if request_id:
        cacheado = models.verificar_idempotencia(request_id)
        if cacheado is not None:
            with log_tool_call(tool_name, cache_hit=True, **contexto):
                pass
            return cacheado
    resultado = _seguro(fn, tool_name, **contexto)
    if request_id:
        models.salvar_idempotencia(request_id, tool_name, payload, resultado)
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# Seed do exemplo "Piemarta"
# ─────────────────────────────────────────────────────────────────────────────


def seed_exemplo() -> int:
    """Insere a obra fictícia 'Piemarta' se o banco estiver vazio (idempotente)."""
    if models.listar_todos():
        return 0

    amostra: list[tuple[Any, ...]] = [
        ("1",       None,  1, "FR-001", "BLOCO-A", "fundacao",   "FUNDAÇÕES",           "conj", None),
        ("1.1",     "1",   2, "FR-001", "BLOCO-A", "fundacao",   "SAPATAS",             "conj", None),
        ("1.1.1",   "1.1", 3, "FR-001", "BLOCO-A", "fundacao",   "ESCAVAÇÃO SAPATAS",   "m³", 1280.0),
        ("1.1.2",   "1.1", 3, "FR-001", "BLOCO-A", "fundacao",   "CONCRETO SAPATAS",    "m³", 240.0),
        ("1.2",     "1",   2, "FR-001", "BLOCO-A", "estrutura",  "VIGAS BALDRAME",      "conj", None),
        ("1.2.1",   "1.2", 3, "FR-001", "BLOCO-A", "estrutura",  "CONCRETO VIGAS",      "m³", 86.0),
        ("2",       None,  1, "FR-002", "BLOCO-B", "estrutura",  "ESTRUTURA",           "conj", None),
        ("2.1",     "2",   2, "FR-002", "BLOCO-B", "estrutura",  "PILARES",             "conj", None),
        ("2.1.1",   "2.1", 3, "FR-002", "BLOCO-B", "estrutura",  "CONCRETO PILARES",    "m³", 520.0),
    ]
    for linha in amostra:
        models.inserir_nodo(
            {
                "eap_id": linha[0], "parent_id": linha[1], "nivel": linha[2],
                "frente_id": linha[3], "local_id": linha[4], "tipo_frente": linha[5],
                "nome": linha[6], "unidade": linha[7], "quantidade": linha[8],
            }
        )
    # Metadados do projeto de exemplo (default ja tem linha via auto-registro).
    try:
        models.atualizar_projeto(
            "default", nome="Piemarta (exemplo)", tipo_obra="edificio_residencial",
        )
    except Exception:
        pass
    return len(amostra)


def seed_templates() -> int:
    """Insere exemplos reais de EAP se a tabela estiver vazia."""
    if models.contar_templates() > 0:
        return 0

    templates = [
        # Casa residencial - fundacao
        ("casa", 80, 150, "alvenaria_estrutural", "sudeste", "1.1", "Escavacao sapatas", "m³", 48.5, 12.0, "0.8 h/m³", "composicao_tipo"),
        ("casa", 80, 150, "alvenaria_estrutural", "sudeste", "1.2", "Concreto sapatas", "m³", 12.3, 3.0, "1.2 h/m³", "composicao_tipo"),
        ("casa", 80, 150, "alvenaria_estrutural", "sudeste", "1.3", "Aco sapatas", "kg", 850.0, 200.0, None, "composicao_tipo"),
        # Casa residencial - estrutura
        ("casa", 80, 150, "alvenaria_estrutural", "sudeste", "2.1", "Pilares concreto", "m³", 8.5, 2.0, "2.5 h/m³", "composicao_tipo"),
        ("casa", 80, 150, "alvenaria_estrutural", "sudeste", "2.2", "Vigas concreto", "m³", 14.0, 3.5, "2.0 h/m³", "composicao_tipo"),
        ("casa", 80, 150, "alvenaria_estrutural", "sudeste", "2.3", "Laje pre-moldada", "m²", 100.0, 15.0, "0.4 h/m²", "composicao_tipo"),
        # Casa residencial - alvenaria
        ("casa", 80, 150, "alvenaria_estrutural", "sudeste", "3.1", "Blocos 6 furos", "m²", 185.0, 30.0, "0.5 h/m²", "composicao_tipo"),
        ("casa", 80, 150, "alvenaria_estrutural", "sudeste", "3.2", "Vergas e contravergas", "ml", 42.0, 10.0, None, "composicao_tipo"),
        # Casa residencial - cobertura
        ("casa", 80, 150, None, None, "4.1", "Estrutura metalica", "conj", 1.0, 0.0, None, "composicao_tipo"),
        ("casa", 80, 150, None, None, "4.2", "Telhas ceramica", "m²", 120.0, 20.0, "0.3 h/m²", "composicao_tipo"),
        # Casa residencial - instalacoes
        ("casa", 80, 150, None, None, "5.1", "Eletrica", "conj", 1.0, 0.0, None, "composicao_tipo"),
        ("casa", 80, 150, None, None, "5.2", "Hidraulica", "conj", 1.0, 0.0, None, "composicao_tipo"),
        ("casa", 80, 150, None, None, "5.3", "Esgoto", "conj", 1.0, 0.0, None, "composicao_tipo"),
        # Casa residencial - acabamento
        ("casa", 80, 150, None, None, "6.1", "Chapisco", "m²", 360.0, 50.0, "0.08 h/m²", "composicao_tipo"),
        ("casa", 80, 150, None, None, "6.2", "Reboco", "m²", 360.0, 50.0, "0.12 h/m²", "composicao_tipo"),
        ("casa", 80, 150, None, None, "6.3", "Piso ceramico", "m²", 85.0, 15.0, "0.25 h/m²", "composicao_tipo"),
        ("casa", 80, 150, None, None, "6.4", "Pintura", "m²", 280.0, 40.0, "0.05 h/m²", "composicao_tipo"),
        # Apartamento - concreto armado
        ("apartamento", 60, 120, "concreto_armado", "sul", "2.1", "Laje pre-moldada", "m²", 80.0, 10.0, "0.4 h/m²", "composicao_tipo"),
        ("apartamento", 60, 120, "concreto_armado", "sul", "2.2", "Concreto laje", "m³", 8.5, 2.0, "1.0 h/m³", "composicao_tipo"),
        # Reforma
        ("reforma", 40, 200, None, None, "1.1", "Remocao piso existente", "m²", 65.0, 20.0, "0.15 h/m²", "composicao_tipo"),
        ("reforma", 40, 200, None, None, "1.2", "Remocada bancada cozinha", "un", 1.0, 0.0, None, "composicao_tipo"),
        ("reforma", 40, 200, None, None, "4.1", "Piso vinilico", "m²", 45.0, 10.0, "0.20 h/m²", "composicao_tipo"),
        ("reforma", 40, 200, None, None, "4.4", "Pintura geral", "m²", 180.0, 30.0, "0.05 h/m²", "composicao_tipo"),
    ]
    for t in templates:
        models.inserir_template({
            "projeto_tipo": t[0], "area_m2_min": t[1], "area_m2_max": t[2],
            "metodo_construtivo": t[3], "regiao": t[4], "eap_node": t[5],
            "nome": t[6], "unidade": t[7], "quantidade_media": t[8],
            "desvio_padrao": t[9], "produtividade": t[10], "fonte": t[11],
        })
    return len(templates)


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def criar_eap_node(
    nome: Annotated[str, Field(description="Descrição legível do item da EAP.", examples=["Sapata S1"])],
    parent_id: Annotated[str | None, Field(description="EAP_ID do nó pai. Nulo/omitido = raiz.", examples=["1.1"])] = None,
    frente_id: Annotated[str, Field(description="Frente de serviço.", examples=["FR-001"])] = "",
    local_id: Annotated[str | None, Field(description="Local/ambiente.", examples=["BLOCO-A"])] = None,
    tipo_frente: Annotated[str, Field(description="Tipo de serviço, ex.: fundacao.", examples=["fundacao"])] = "",
    unidade: Annotated[str | None, Field(description="Unidade de medida (m², m³, un...).", examples=["m³"])] = None,
    quantidade: Annotated[float | None, Field(description="Quantidade planejada (>= 0).", ge=0)] = None,
    nao_aplicavel: Annotated[bool | None, Field(description="True = pacote N/A (verba/provisório); folha sem quantidade e sem N/A gera aviso FANTASMA.")] = None,
    motivo_na: Annotated[str | None, Field(description="Motivo do N/A (ex.: provisório, verba).")] = None,
    request_id: Annotated[str | None, Field(description="Idempotência: mesmo request_id retorna a mesma resposta (evita duplicar em retry).")] = None,
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = projeto 'default'.", examples=["default"])] = None,
) -> dict[str, Any]:
    """Cria um nó na EAP.

    Gera o ``EAP_ID`` hierárquico (ex.: "1.2.3"), calcula o ``NIVEL`` como
    ``pai.nivel + 1`` (ou 1 para raiz) e persiste o nó. Reenviar o mesmo
    ``request_id`` devolve a resposta anterior em vez de duplicar o nó.
    """

    def _executar() -> dict[str, Any]:
        pid = project_id or models.DEFAULT_PROJECT_ID
        dados = schemas.CriarEAPNodeInput(
            parent_id=parent_id, frente_id=frente_id, local_id=local_id,
            tipo_frente=tipo_frente, nome=nome, unidade=unidade, quantidade=quantidade,
            nao_aplicavel=nao_aplicavel, motivo_na=motivo_na,
        )

        if dados.parent_id is not None:
            pai = models.buscar_por_eap_id(dados.parent_id, pid)
            if pai is None:
                return schemas.ErroOutput(
                    erro=f"PARENT_ID '{dados.parent_id}' não existe na EAP."
                ).model_dump()
            nivel = pai["nivel"] + 1
        else:
            nivel = 1

        eap_id = models.proximo_eap_id(dados.parent_id, pid)
        novo = models.inserir_nodo(
            {
                "eap_id": eap_id, "parent_id": dados.parent_id, "nivel": nivel,
                "project_id": pid,
                "frente_id": dados.frente_id, "local_id": dados.local_id,
                "tipo_frente": dados.tipo_frente, "nome": dados.nome,
                "unidade": dados.unidade, "quantidade": dados.quantidade,
                "nao_aplicavel": dados.nao_aplicavel, "motivo_na": dados.motivo_na,
            }
        )
        return schemas.EAPNodeOutput.model_validate(novo).model_dump()

    payload = {
        "nome": nome, "parent_id": parent_id, "frente_id": frente_id,
        "local_id": local_id, "tipo_frente": tipo_frente,
        "unidade": unidade, "quantidade": quantidade,
    }
    return _idempotente(request_id, "criar_eap_node", payload, _executar)


@mcp.tool()
def get_eap_node(
    eap_id: Annotated[str | None, Field(description="EAP_ID (código display) do nó, ex.: '1.2.3'.", examples=["1.2.3"])] = None,
    uid: Annotated[str | None, Field(description="UID estável do nó (referência imutável; não muda em movimentações).", examples=["9f2c..."])] = None,
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = projeto 'default'.", examples=["default"])] = None,
) -> dict[str, Any]:
    """Retorna um nó por ``uid`` OU por ``eap_id``.

    Prefira ``uid`` (estável). Se o ``eap_id`` informado não existir mais,
    consulta o histórico de movimentação e devolve o nó atual com
    ``movido_de``/``movido_para``.
    """

    def _executar() -> dict[str, Any]:
        pid = project_id or models.DEFAULT_PROJECT_ID
        if uid:
            node = models.buscar_por_uid(uid, pid)
            if node is None:
                return schemas.ErroOutput(erro=f"Nó UID '{uid}' não encontrado.").model_dump()
            return schemas.EAPNodeOutput.model_validate(node).model_dump()
        if not eap_id:
            return schemas.ErroOutput(erro="Informe 'uid' ou 'eap_id'.").model_dump()
        node = models.buscar_por_eap_id(eap_id, pid)
        if node is not None:
            return schemas.EAPNodeOutput.model_validate(node).model_dump()
        hist = models.historico_movimentos(project_id=pid, eap_id_de=eap_id)
        if hist:
            atual = models.buscar_por_uid(hist[0]["uid"], pid)
            if atual is not None:
                saida = schemas.EAPNodeOutput.model_validate(atual).model_dump()
                saida["movido_de"] = eap_id
                saida["movido_para"] = atual["eap_id"]
                return saida
        return schemas.ErroOutput(erro=f"Nó EAP '{eap_id}' não encontrado.").model_dump()

    return _seguro(_executar, "get_eap_node")


@mcp.tool()
def get_eap_tree(
    eap_id: Annotated[str | None, Field(description="Opcional: subárvore deste nó; omitido = árvore inteira.", examples=["1"])] = None,
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = projeto 'default'.", examples=["default"])] = None,
    max_profundidade: Annotated[int | None, Field(description="Limita quantos níveis de filhos são expandidos (1 = só a raiz). Omitido = sem limite. Use para árvores grandes: nós cortados vêm com truncado=True e total_descendentes, e podem ser expandidos chamando de novo com eap_id=<esse nó>.", ge=1)] = None,
) -> dict[str, Any]:
    """Retorna a EAP em estrutura JSON aninhada (inteira ou subárvore).

    Em árvores grandes, use ``max_profundidade`` para evitar respostas
    gigantes — os nós truncados indicam quantos descendentes têm.
    """

    def _executar() -> dict[str, Any]:
        pid = project_id or models.DEFAULT_PROJECT_ID
        raizes = models.montar_arvore(eap_id, pid, max_profundidade=max_profundidade)
        return schemas.ArvoreEAPOutput(raizes=raizes).model_dump()

    return _seguro(_executar, "get_eap_tree", project_id=project_id, eap_id=eap_id)


@mcp.tool()
def validar_estrutura(
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = projeto 'default'.", examples=["default"])] = None,
) -> dict[str, Any]:
    """Audita a árvore: problemas estruturais (órfãos, duplicidades, NIVEL) e
    avisos semânticos (múltiplas raízes, CAIXA ALTA, unidade de agregador)."""

    def _executar() -> dict[str, Any]:
        resultado = models.validar_estrutura(project_id)
        return schemas.ValidarEstruturaOutput.model_validate(resultado).model_dump()

    return _seguro(_executar, "validar_estrutura")


@mcp.tool()
def listar_por_tipo_frente(
    tipo_frente: Annotated[str, Field(description="Tipo de serviço a filtrar, ex.: 'estrutura'.", examples=["estrutura"], min_length=1)],
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = projeto 'default'.", examples=["default"])] = None,
) -> dict[str, Any]:
    """Retorna todos os nós de um TIPO_FRENTE em qualquer parte da árvore.

    Retorna envelope ``{tipo_frente, total, nos}``. Lista vazia é resultado válido.
    """

    def _executar() -> dict[str, Any]:
        pid = project_id or models.DEFAULT_PROJECT_ID
        nodes = models.listar_por_tipo_frente(tipo_frente, pid)
        return schemas.ListarPorTipoFrenteOutput(
            tipo_frente=tipo_frente, total=len(nodes),
            nos=[schemas.EAPNodeOutput.model_validate(n) for n in nodes],
        ).model_dump()

    return _seguro(_executar, "listar_por_tipo_frente")


@mcp.tool()
def buscar_eap_node(
    termo: Annotated[str, Field(description="Texto a procurar em nome, EAP_ID, frente, local ou responsável. Acento e caixa são ignorados: 'escavacao' acha 'Escavação Sapatas'.", examples=["escavacao"], min_length=1)],
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = projeto 'default'.", examples=["default"])] = None,
) -> dict[str, Any]:
    """Busca nós por termo (substring) em nome, EAP_ID, frente_id, local_id
    ou responsável.

    Retorna envelope ``{termo, total, nos}``. Lista vazia é resultado válido.
    """

    def _executar() -> dict[str, Any]:
        pid = project_id or models.DEFAULT_PROJECT_ID
        nodes = models.buscar_eap_node(termo, pid)
        return schemas.BuscarEAPNodeOutput(
            termo=termo, total=len(nodes),
            nos=[schemas.EAPNodeOutput.model_validate(n) for n in nodes],
        ).model_dump()

    return _seguro(_executar, "buscar_eap_node")


# ─────────────────────────────────────────────────────────────────────────────
# CRUD completo (tools de manutenção da EAP)
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def atualizar_eap_node(
    eap_id: Annotated[str, Field(description="Código hierárquico do nó a atualizar, ex.: '1.1.1'.", examples=["1.1.1"])],
    nome: Annotated[str | None, Field(description="Nova descrição legível.", examples=["Sapata S1B"])] = None,
    frente_id: Annotated[str | None, Field(description="Nova frente de serviço.", examples=["FR-001"])] = None,
    local_id: Annotated[str | None, Field(description="Novo local/ambiente.", examples=["BLOCO-A"])] = None,
    tipo_frente: Annotated[str | None, Field(description="Novo tipo de serviço (fundacao, estrutura, alvenaria...).", examples=["fundacao"])] = None,
    unidade: Annotated[str | None, Field(description="Nova unidade (m², m³, ml, un, kg, conj, vb, pt).", examples=["m³"])] = None,
    quantidade: Annotated[float | None, Field(description="Nova quantidade planejada (>= 0); só em nós-folha.", ge=0)] = None,
    nao_aplicavel: Annotated[bool | None, Field(description="Novo estado N/A (True/False).")] = None,
    motivo_na: Annotated[str | None, Field(description="Novo motivo do N/A.")] = None,
    request_id: Annotated[str | None, Field(description="Idempotência: mesmo request_id retorna a mesma resposta (evita duplicar em retry).")] = None,
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = projeto 'default'.", examples=["default"])] = None,
) -> dict[str, Any]:
    """Atualiza campos de um nó existente sem alterar a hierarquia.

    Passe apenas os campos a alterar. Valida unidade e tipo_frente no
    vocabulário fechado e rejeita quantidade em nó com filhos.
    """

    def _executar() -> dict[str, Any]:
        pid = project_id or models.DEFAULT_PROJECT_ID
        dados = {k: v for k, v in {
            "nome": nome, "frente_id": frente_id, "local_id": local_id,
            "tipo_frente": tipo_frente, "unidade": unidade, "quantidade": quantidade,
            "nao_aplicavel": nao_aplicavel, "motivo_na": motivo_na,
        }.items() if v is not None}
        dados["project_id"] = pid
        if not dados:
            atual = models.buscar_por_eap_id(eap_id, pid)
            if atual is None:
                return schemas.ErroOutput(erro=f"Nó EAP '{eap_id}' não encontrado.").model_dump()
            return schemas.EAPNodeOutput.model_validate(atual).model_dump()
        novo = models.atualizar_nodo(eap_id, dados)
        return schemas.EAPNodeOutput.model_validate(novo).model_dump()

    payload = {
        "eap_id": eap_id, "nome": nome, "frente_id": frente_id, "local_id": local_id,
        "tipo_frente": tipo_frente, "unidade": unidade, "quantidade": quantidade,
    }
    return _idempotente(request_id, "atualizar_eap_node", payload, _executar)


@mcp.tool()
def deletar_eap_node(
    eap_id: Annotated[str, Field(description="Código hierárquico do nó a deletar, ex.: '1.1.3'.", examples=["1.1.3"])],
    cascade: Annotated[bool, Field(description="Se True, deleta o nó e todos os descendentes. Se False, pede folha.")] = False,
    request_id: Annotated[str | None, Field(description="Idempotência: mesmo request_id retorna a mesma resposta (evita duplicar em retry).")] = None,
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = projeto 'default'.", examples=["default"])] = None,
) -> dict[str, Any]:
    """Deleta um nó da EAP.

    Com ``cascade=True`` remove toda a subárvore; com ``cascade=False`` só
    permite deletar nós-folha (sem filhos).
    """

    def _executar() -> dict[str, Any]:
        pid = project_id or models.DEFAULT_PROJECT_ID
        return models.deletar_nodo(eap_id, cascade=cascade, project_id=pid)

    return _idempotente(
        request_id, "deletar_eap_node",
        {"eap_id": eap_id, "cascade": cascade}, _executar,
    )


@mcp.tool()
def move_eap_node(
    eap_id: Annotated[str, Field(description="Codigo hierarquico do no a mover, ex.: '1.2'.", examples=["1.2"])],
    novo_parent_id: Annotated[str | None, Field(description="EAP_ID do novo pai. Nulo/omitido = mover para a raiz (vira no de topo).", examples=["2.1", None])] = None,
    motivo: Annotated[str | None, Field(description="Motivo da movimentacao (registrado em eap_id_history).", examples=["reorganizacao de frentes"])] = None,
    request_id: Annotated[str | None, Field(description="Idempotencia: mesmo request_id retorna a mesma resposta (evita duplicar em retry).")] = None,
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = projeto 'default'.", examples=["default"])] = None,
) -> dict[str, Any]:
    """Move um no (e toda a sua subarvore) para um novo pai.

    O ``uid`` de cada no e ESTAVEL (referencia externa imutavel): apenas o
    ``EAP_ID``/``NIVEL`` (display) sao re-renumerados, e o movimento fica
    registrado em ``eap_id_history`` (auditoria: get_eap_node por eap_id antigo
    devolve o no atual com movido_de/movido_para). Rejeita movimentos que
    criariam ciclo (destino dentro da propria subarvore do no movido).
    """

    def _executar() -> dict[str, Any]:
        pid = project_id or models.DEFAULT_PROJECT_ID
        return models.mover_nodo(eap_id, novo_parent_id, pid, motivo)

    return _idempotente(
        request_id, "move_eap_node",
        {"eap_id": eap_id, "novo_parent_id": novo_parent_id, "motivo": motivo,
         "project_id": project_id}, _executar,
    )


@mcp.tool()
def listar_projetos(
    limit: Annotated[int | None, Field(description="Máximo de projetos a retornar. Omitido = todos (cuidado com muitos projetos).", ge=1, le=500)] = None,
    offset: Annotated[int, Field(description="Quantos projetos pular (para paginar).", ge=0)] = 0,
) -> dict[str, Any]:
    """Lista projetos cadastrados e a contagem de nós de cada um.

    Retorna ``total_projetos`` (contagem geral, ignorando paginação) junto
    com ``projetos`` (só a página pedida) — use para saber se há mais páginas.
    """
    def _executar() -> dict[str, Any]:
        projetos = models.listar_projetos(limit=limit, offset=offset)
        total_nos = sum(p["total_nos"] for p in projetos)
        return {
            "projetos": projetos,
            "total_projetos": models.contar_projetos(),
            "retornados": len(projetos),
            "offset": offset,
            "total_nos": total_nos,
        }

    return _seguro(_executar, "listar_projetos", limit=limit, offset=offset)


@mcp.tool()
def deletar_projeto(
    project_id: Annotated[str, Field(description="Identificador do projeto a remover, ex.: 'default'.", examples=["default"])],
    request_id: Annotated[str | None, Field(description="Idempotência: mesmo request_id retorna a mesma resposta (evita duplicar em retry).")] = None,
) -> dict[str, Any]:
    """Deleta TODOS os nós de um projeto. Operação irreversível."""
    def _executar() -> dict[str, Any]:
        return models.deletar_projeto(project_id)

    return _idempotente(
        request_id, "deletar_projeto", {"project_id": project_id}, _executar,
    )


@mcp.tool()
def criar_projeto(
    project_id: Annotated[str, Field(description="Identificador único do projeto (obra). Use letras, números, hífen ou underscore.", examples=["residencial-jardim", "default"])],
    nome: Annotated[str | None, Field(description="Nome legível da obra. Default: igual a project_id.", examples=["Residencial Jardim das Flores"])] = None,
    tipo_obra: Annotated[str | None, Field(description="Tipo da obra, ex.: casa, apartamento, reforma, edificio_comercial.", examples=["casa"])] = None,
    area_m2: Annotated[float | None, Field(description="Área construída em m².", ge=0)] = None,
    metodo_construtivo: Annotated[str | None, Field(description="Método construtivo, ex.: alvenaria_estrutural.", examples=["alvenaria_estrutural"])] = None,
    regiao: Annotated[str | None, Field(description="Região do projeto, ex.: sudeste.", examples=["sudeste"])] = None,
    cliente: Annotated[str | None, Field(description="Cliente ou incorporadora.", examples=["Cliente Exemplo LTDA"])] = None,
) -> dict[str, Any]:
    """Cria um novo projeto (obra) com metadados.

    Cada obra vive em seu próprio ``project_id``. Depois de criar, use
    ``project_id`` nas demais tools para trabalhar na EAP da obra.
    """

    def _executar() -> dict[str, Any]:
        projeto = models.criar_projeto(
            project_id,
            nome=nome, tipo_obra=tipo_obra, area_m2=area_m2,
            metodo_construtivo=metodo_construtivo,
            regiao=regiao, cliente=cliente,
        )
        return schemas.ProjetoOutput.model_validate(projeto).model_dump()

    return _seguro(_executar, "criar_projeto")


@mcp.tool()
def atualizar_projeto(
    project_id: Annotated[str, Field(description="Identificador do projeto a atualizar.", examples=["default"])],
    nome: Annotated[str | None, Field(description="Nome legível da obra.", examples=["Residencial Jardim das Flores"])] = None,
    tipo_obra: Annotated[str | None, Field(description="Tipo da obra.", examples=["casa"])] = None,
    area_m2: Annotated[float | None, Field(description="Área construída em m².", ge=0)] = None,
    metodo_construtivo: Annotated[str | None, Field(description="Método construtivo.", examples=["alvenaria_estrutural"])] = None,
    regiao: Annotated[str | None, Field(description="Região do projeto.", examples=["sudeste"])] = None,
    cliente: Annotated[str | None, Field(description="Cliente ou incorporadora.", examples=["Cliente Exemplo LTDA"])] = None,
    ativo: Annotated[bool | None, Field(description="Se False, marca o projeto como inativo (não apaga dados).")] = None,
) -> dict[str, Any]:
    """Atualiza os metadados de um projeto existente."""
    def _executar() -> dict[str, Any]:
        projeto = models.atualizar_projeto(
            project_id,
            nome=nome, tipo_obra=tipo_obra, area_m2=area_m2,
            metodo_construtivo=metodo_construtivo,
            regiao=regiao, cliente=cliente,
            ativo=(1 if ativo else 0) if ativo is not None else None,
        )
        return schemas.ProjetoOutput.model_validate(projeto).model_dump()

    return _seguro(_executar, "atualizar_projeto")


@mcp.tool()
def definir_criterio(
    eap_id: Annotated[str | None, Field(description="EAP_ID do nó (display).", examples=["1.1.1"])] = None,
    uid: Annotated[str | None, Field(description="UID estável do nó (preferível).", examples=["a1b2..."])] = None,
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = 'default'.", examples=["default"])] = None,
    descricao: Annotated[str | None, Field(description="Dicionário do pacote: o que está (e não está) incluído.")] = None,
    criterio_medicao: Annotated[str | None, Field(description="Critério de medição (vãos descontados, perdas, faixas).")] = None,
    responsavel: Annotated[str | None, Field(description="Dono/OBS do pacote (quem executa e é cobrado).")] = None,
    disciplina: Annotated[str | None, Field(description="Disciplina técnica (civil, eletrica, hidraulica...).")] = None,
) -> dict[str, Any]:
    """Define o dicionário e o dono de um pacote (nó).

    Preenche campos opcionais de WBS dictionary (``descricao``,
    ``criterio_medicao``) e de OBS (``responsavel``, ``disciplina``).
    Aceita ``eap_id`` OU ``uid``.
    """

    def _executar() -> dict[str, Any]:
        pid = project_id or models.DEFAULT_PROJECT_ID
        if uid:
            node = models.buscar_por_uid(uid, pid)
        elif eap_id:
            node = models.buscar_por_eap_id(eap_id, pid)
        else:
            return schemas.ErroOutput(erro="Informe 'uid' ou 'eap_id'.").model_dump()
        if node is None:
            return schemas.ErroOutput(erro="Nó não encontrado no projeto.").model_dump()
        campos = {k: v for k, v in {
            "descricao": descricao, "criterio_medicao": criterio_medicao,
            "responsavel": responsavel, "disciplina": disciplina,
        }.items() if v is not None}
        if not campos:
            return schemas.ErroOutput(
                erro="Informe ao menos um campo (descricao, criterio_medicao, responsavel, disciplina)."
            ).model_dump()
        novo = models.atualizar_nodo(node["eap_id"], {**campos, "project_id": pid})
        return schemas.EAPNodeOutput.model_validate(novo).model_dump()

    return _seguro(_executar, "definir_criterio")


@mcp.tool()
def pacotes_sem_dono(
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = 'default'.", examples=["default"])] = None,
) -> dict[str, Any]:
    """Lista pacotes (folhas mensuráveis) que ainda NÃO têm responsável (OBS)."""

    def _executar() -> dict[str, Any]:
        pid = project_id or models.DEFAULT_PROJECT_ID
        nos = models.listar_pacotes_sem_dono(pid)
        return {
            "project_id": pid,
            "total": len(nos),
            "nos": [schemas.EAPNodeOutput.model_validate(n).model_dump() for n in nos],
        }

    return _seguro(_executar, "pacotes_sem_dono")


@mcp.tool()
def resumo_quantitativos(
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = 'default'.", examples=["default"])] = None,
    tipo_frente: Annotated[str | None, Field(description="Filtra por tipo de frente (ex.: fundacao).", examples=["fundacao"])] = None,
) -> dict[str, Any]:
    """Resumo de quantitativos por (tipo_frente, unidade).

    Considera SÓ folhas; ``quantidade=null`` é ignorado; nunca mistura unidades
    (RICS NRM). ``quantidade=0`` conta como zero real (sem FANTASMA).
    """

    def _executar() -> dict[str, Any]:
        pid = project_id or models.DEFAULT_PROJECT_ID
        grupos = models.resumo_quantitativos(pid, tipo_frente)
        return {"project_id": pid, "total_grupos": len(grupos), "grupos": grupos}

    return _seguro(_executar, "resumo_quantitativos")


@mcp.tool()
def registrar_retrabalho(
    motivo: Annotated[str, Field(description="Motivo do retrabalho (obrigatório).", examples=["infiltração em reboco"])],
    eap_id: Annotated[str | None, Field(description="EAP_ID do nó original.", examples=["1.1.1"])] = None,
    uid: Annotated[str | None, Field(description="UID estável do nó original (preferível).")] = None,
    project_id: Annotated[str | None, Field(description="Projeto (obra). Omitir = 'default'.", examples=["default"])] = None,
) -> dict[str, Any]:
    """Registra retrabalho como IRMÃO ``R{n}`` do nó original (mesmo pai).

    Original NUNCA é alterado/apagado: R{n} recebe ``origem_uid`` linkando ao
    original, herda unidade/quantidade, ``status=retrabalho``, ``revisao`` e
    ``motivo``. R é folha legítima: não viola folha/quantidade nem conta como
    duplicidade. ``resumo_quantitativos`` separa previsto × retrabalho.
    """

    def _executar() -> dict[str, Any]:
        novo = models.registrar_retrabalho(
            eap_id=eap_id, uid=uid, project_id=project_id, motivo=motivo,
        )
        return schemas.EAPNodeOutput.model_validate(novo).model_dump()

    return _seguro(_executar, "registrar_retrabalho")


@mcp.tool()
def listar_templates(
    projeto_tipo: Annotated[str | None, Field(description="Tipo de obra p/ filtrar (casa, apartamento, reforma).", examples=["casa"])] = None,
    area_m2: Annotated[float | None, Field(description="Área construída (m²) p/ filtrar template compatível.", ge=0)] = None,
    metodo_construtivo: Annotated[str | None, Field(description="Método construtivo, ex.: alvenaria_estrutural.", examples=["alvenaria_estrutural"])] = None,
    limit: Annotated[int | None, Field(description="Máximo de templates a retornar. Omitido = todos.", ge=1, le=500)] = None,
    offset: Annotated[int, Field(description="Quantos templates pular (para paginar).", ge=0)] = 0,
) -> dict[str, Any]:
    """Lista templates de EAP reais (referência histórica de orçamento).

    ``total`` reflete o total que casa com os filtros (ignorando paginação);
    ``retornados`` é o tamanho da página atual.
    """
    def _executar() -> dict[str, Any]:
        templates = models.listar_templates(
            projeto_tipo, area_m2, metodo_construtivo, limit=limit, offset=offset
        )
        total = models.contar_templates_filtrados(projeto_tipo, area_m2, metodo_construtivo)
        return {
            "templates": templates,
            "total": total,
            "retornados": len(templates),
            "offset": offset,
        }

    return _seguro(
        _executar, "listar_templates",
        projeto_tipo=projeto_tipo, limit=limit, offset=offset,
    )


# ─────────────────────────────────────────────────────────────────────────────
# App ASGI para uvicorn (streamable-http)
# ─────────────────────────────────────────────────────────────────────────────


models.init_db()
_seedados = seed_exemplo()
_seed_templates = seed_templates()
_idem_limpos = models.limpar_idempotencia_antiga()

# ``streamable_http_app()`` devolve uma Starlette ASGI application que serve
# o protocolo MCP streamable-http. Esta é a app que o uvicorn/Render vai servir.
app = mcp.streamable_http_app()


def main() -> None:
    """Sobe o servidor com uvicorn, escutando em ``0.0.0.0:PORT``."""
    import uvicorn  # importado aqui para manter requirements mínimos

    porta = int(os.environ.get("PORT", "10000"))
    host = os.environ.get("HOST", "0.0.0.0")

    if _seedados:
        print(
            f"[eap-mcp-server] Banco inicializado com {_seedados} nós de exemplo ('Piemarta').",
            file=sys.stderr, flush=True,
        )
    else:
        print("[eap-mcp-server] Banco já populado; mantido como está.", file=sys.stderr, flush=True)

    if _seed_templates:
        print(
            f"[eap-mcp-server] Templates de referência carregados: {_seed_templates}.",
            file=sys.stderr, flush=True,
        )

    if _idem_limpos:
        print(
            f"[eap-mcp-server] Registros de idempotência antigos removidos: {_idem_limpos}.",
            file=sys.stderr, flush=True,
        )

    uvicorn.run(app, host=host, port=porta)


if __name__ == "__main__":
    main()
