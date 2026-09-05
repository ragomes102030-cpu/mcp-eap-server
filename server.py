"""Servidor MCP (Model Context Protocol) de EAP para obras de construção civil.

Esta é a versão HTTP/streamable do servidor, projetada para deploy em nuvem
(Render, Railway, Fly.io etc.). O servidor original ``mcp-eap`` (Desktop) usa
stdio local; esta versão troca o transporte para ``streamable-http`` expondo
uma app ASGI (Starlette) que pode ser servida por uvicorn.

Ferramentas expostas (mesmas 5 do servidor local):

  * criar_eap_node         cria nó, gera EAP_ID hierárquico e calcula NIVEL
  * get_eap_tree           retorna a árvore em JSON aninhado
  * get_eap_node           retorna um nó específico
  * validar_estrutura      detecta órfãos, duplicidades e NIVEL inconsistente
  * listar_por_tipo_frente filtra nós por tipo de frente de serviço

Variáveis de ambiente:
  * PORT — porta TCP (padrão 10000). O Render injeta automaticamente.

Como rodar:
  * Local:           ``python server.py``
  * Com uvicorn:     ``uvicorn server:app --host 0.0.0.0 --port 10000``
  * Procfile Render: ``web: uvicorn server:app --host 0.0.0.0 --port $PORT``
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

# ─────────────────────────────────────────────────────────────────────────────
# Servidor FastMCP
# ─────────────────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="eap-server",
    instructions=(
        "Servidor MCP de Estrutura Analítica do Projeto (EAP) de obras. "
        "Gerencia nós hierárquicos (EAP_ID no formato '1.2.3') com PARENT_ID, "
        "NIVEL, FRENTE_ID, LOCAL_ID, TIPO_FRENTE, NOME, UNIDADE e QUANTIDADE. "
        "Use criar_eap_node para inserir, get_eap_tree para navegar, "
        "get_eap_node para detalhe, validar_estrutura para auditoria de "
        "integridade e listar_por_tipo_frente para agrupar por tipo de serviço."
    ),
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
            "mcp-eap-server.onrender.com:*",
        ],
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
            "http://mcp-eap-server.onrender.com:*",
            "https://mcp-eap-server.onrender.com:*",
        ],
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Wrapper central de erro — reaproveitado por TODAS as tools.
# Nenhuma tool lança exceção ao protocolo: em qualquer falha devolve
# {"erro": "<mensagem>"}.
# ─────────────────────────────────────────────────────────────────────────────


def _seguro(fn: Callable[[], Any]) -> dict[str, Any]:
    """Executa ``fn`` e converte qualquer exceção em resposta de erro."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return schemas.ErroOutput(erro=str(exc)).model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# Seed do exemplo "Piemarta"
# ─────────────────────────────────────────────────────────────────────────────


def seed_exemplo() -> int:
    """Insere a obra fictícia 'Piemarta' se o banco estiver vazio (idempotente)."""
    if models.listar_todos():
        return 0

    amostra: list[tuple[Any, ...]] = [
        ("1",       None,  1, "FR-001", "BLOCO-A", "fundacao",  "FUNDAÇÕES",        "conj", None),
        ("1.1",     "1",   2, "FR-001", "BLOCO-A", "fundacao",  "SAPATAS",          "conj", 24),
        ("1.1.1",   "1.1", 3, "FR-001", "BLOCO-A", "fundacao",  "ESCAVAÇÃO SAPATAS", "m³", 1280.0),
        ("1.1.2",   "1.1", 3, "FR-001", "BLOCO-A", "estrutura", "CONCRETO SAPATAS",  "m³", 240.0),
        ("1.2",     "1",   2, "FR-001", "BLOCO-A", "estrutura", "VIGAS BALDRAME",    "ml", 320.0),
        ("1.2.1",   "1.2", 3, "FR-001", "BLOCO-A", "estrutura", "CONCRETO VIGAS",    "m³", 86.0),
        ("2",       None,  1, "FR-002", "BLOCO-B", "estrutura", "ESTRUTURA",         "conj", None),
        ("2.1",     "2",   2, "FR-002", "BLOCO-B", "estrutura", "PILARES",           "un", 42),
        ("2.1.1",   "2.1", 3, "FR-002", "BLOCO-B", "estrutura", "CONCRETO PILARES",  "m³", 520.0),
    ]
    for linha in amostra:
        models.inserir_nodo(
            {
                "eap_id": linha[0], "parent_id": linha[1], "nivel": linha[2],
                "frente_id": linha[3], "local_id": linha[4], "tipo_frente": linha[5],
                "nome": linha[6], "unidade": linha[7], "quantidade": linha[8],
            }
        )
    return len(amostra)


# ─────────────────────────────────────────────────────────────────────────────
# Tools — cópia fiel da versão stdio (eap-mcp)
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
) -> dict[str, Any]:
    """Cria um nó na EAP.

    Gera o ``EAP_ID`` hierárquico (ex.: "1.2.3"), calcula o ``NIVEL`` como
    ``pai.nivel + 1`` (ou 1 para raiz) e persiste o nó.
    """

    def _executar() -> dict[str, Any]:
        dados = schemas.CriarEAPNodeInput(
            parent_id=parent_id, frente_id=frente_id, local_id=local_id,
            tipo_frente=tipo_frente, nome=nome, unidade=unidade, quantidade=quantidade,
        )

        if dados.parent_id is not None:
            pai = models.buscar_por_eap_id(dados.parent_id)
            if pai is None:
                return schemas.ErroOutput(
                    erro=f"PARENT_ID '{dados.parent_id}' não existe na EAP."
                ).model_dump()
            nivel = pai["nivel"] + 1
        else:
            nivel = 1

        eap_id = models.proximo_eap_id(dados.parent_id)
        novo = models.inserir_nodo(
            {
                "eap_id": eap_id, "parent_id": dados.parent_id, "nivel": nivel,
                "frente_id": dados.frente_id, "local_id": dados.local_id,
                "tipo_frente": dados.tipo_frente, "nome": dados.nome,
                "unidade": dados.unidade, "quantidade": dados.quantidade,
            }
        )
        return schemas.EAPNodeOutput.model_validate(novo).model_dump()

    return _seguro(_executar)


@mcp.tool()
def get_eap_node(
    eap_id: Annotated[str, Field(description="Código hierárquico do nó, ex.: '1.2.3'.", examples=["1.2.3"])],
) -> dict[str, Any]:
    """Retorna os dados de um nó específico da EAP."""

    def _executar() -> dict[str, Any]:
        node = models.buscar_por_eap_id(eap_id)
        if node is None:
            return schemas.ErroOutput(erro=f"Nó EAP '{eap_id}' não encontrado.").model_dump()
        return schemas.EAPNodeOutput.model_validate(node).model_dump()

    return _seguro(_executar)


@mcp.tool()
def get_eap_tree(
    eap_id: Annotated[str | None, Field(description="Opcional: subárvore deste nó; omitido = árvore inteira.", examples=["1"])] = None,
) -> dict[str, Any]:
    """Retorna a EAP em estrutura JSON aninhada (inteira ou subárvore)."""

    def _executar() -> dict[str, Any]:
        raizes = models.montar_arvore(eap_id)
        return schemas.ArvoreEAPOutput(raizes=raizes).model_dump()

    return _seguro(_executar)


@mcp.tool()
def validar_estrutura() -> dict[str, Any]:
    """Percorre a árvore e reporta problemas: órfãos, duplicidades, NIVEL inconsistente."""

    def _executar() -> dict[str, Any]:
        resultado = models.validar_estrutura()
        return schemas.ValidarEstruturaOutput.model_validate(resultado).model_dump()

    return _seguro(_executar)


@mcp.tool()
def listar_por_tipo_frente(
    tipo_frente: Annotated[str, Field(description="Tipo de serviço a filtrar, ex.: 'estrutura'.", examples=["estrutura"], min_length=1)],
) -> dict[str, Any]:
    """Retorna todos os nós de um TIPO_FRENTE em qualquer parte da árvore.

    Retorna envelope ``{tipo_frente, total, nos}``. Lista vazia é resultado válido.
    """

    def _executar() -> dict[str, Any]:
        nodes = models.listar_por_tipo_frente(tipo_frente)
        return schemas.ListarPorTipoFrenteOutput(
            tipo_frente=tipo_frente, total=len(nodes),
            nos=[schemas.EAPNodeOutput.model_validate(n) for n in nodes],
        ).model_dump()

    return _seguro(_executar)


# ─────────────────────────────────────────────────────────────────────────────
# App ASGI para uvicorn (streamable-http)
# ─────────────────────────────────────────────────────────────────────────────


models.init_db()
_seedados = seed_exemplo()

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

    uvicorn.run(app, host=host, port=porta)


if __name__ == "__main__":
    main()
