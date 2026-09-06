"""Camada de dados SQLite/libSQL para a EAP (Work Breakdown Structure) de obras.

Usa ``libsql_client`` (Turso) em produção quando ``TURSO_URL`` está configurada,
com fallback pro ``sqlite3`` local para desenvolvimento. Toda a lógica de acesso
a dados, a geração dos códigos hierárquicos (``EAP_ID`` no formato "1.2.3"), o
cálculo do nível e a validação de integridade da árvore vivem aqui.

Tabela ``eap_node`` (fiel ao sistema ARES):

    eap_id       TEXT PRIMARY KEY        código hierárquico, ex. "1.2.3"
    parent_id    TEXT REFERENCES eap_node(eap_id)   auto-referência; NULL = raiz
    nivel        INTEGER                 nível armazenado (não calculado em leitura)
    frente_id    TEXT                    frente de serviço
    local_id     TEXT                    local / ambiente
    tipo_frente  TEXT                    classificação do tipo de serviço
    nome         TEXT                    descrição do item
    unidade      TEXT                    unidade de medida (m², m³, un, ...)
    quantidade   REAL                    quantidade planejada
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

DB_PATH = Path(__file__).resolve().parent / "eap.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS eap_node (
    eap_id       TEXT PRIMARY KEY,
    parent_id    TEXT REFERENCES eap_node(eap_id) ON DELETE SET NULL,
    nivel        INTEGER NOT NULL,
    frente_id    TEXT,
    local_id     TEXT,
    tipo_frente  TEXT,
    nome         TEXT NOT NULL,
    unidade      TEXT,
    quantidade   REAL
);
CREATE INDEX IF NOT EXISTS ix_eap_node_parent      ON eap_node(parent_id);
CREATE INDEX IF NOT EXISTS ix_eap_node_tipo_frente ON eap_node(tipo_frente);
"""

_TURSO_URL = os.environ.get("TURSO_URL", "")
_TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "")


class _TursoConn:
    """Wrapper que emula a API sqlite3 usando libsql_client (Turso)."""

    def __init__(self) -> None:
        import libsql_client

        self._client = libsql_client.create_client(
            url=_TURSO_URL, auth_token=_TURSO_TOKEN
        )

    def execute(self, sql: str, params: tuple = ()) -> "_TursoCursor":
        converted = sql
        for i, _ in enumerate(params, start=1):
            converted = converted.replace("?", f":{i}", 1)
        result = self._client.execute(converted, list(params))
        return _TursoCursor(result)

    def executescript(self, script: str) -> None:
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if stmt:
                self.execute(stmt)

    def commit(self) -> None:
        pass

    def __enter__(self) -> "_TursoConn":
        return self

    def __exit__(self, *exc: object) -> None:
        pass


class _TursoCursor:
    """Wrapper de resultado que emula .fetchone() / .fetchall() do sqlite3."""

    def __init__(self, result: Any) -> None:
        self._rows = [dict(zip(result.columns, row)) for row in result.rows]

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


def _connect() -> "_TursoConn | sqlite3.Connection":
    """Abre conexão: Turso (se configurado) ou sqlite3 local."""
    if _TURSO_URL:
        return _TursoConn()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Cria a tabela caso ainda não exista."""
    with _connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# DAO básico
# ─────────────────────────────────────────────────────────────────────────────


def buscar_por_eap_id(eap_id: str) -> dict[str, Any] | None:
    """Retorna um nó pelo EAP_ID, ou None se não existir."""
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM eap_node WHERE eap_id = ?", (eap_id,)
        )
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


def listar_filhos(parent_id: str) -> list[dict[str, Any]]:
    """Retorna os filhos diretos de um nó, ordenados pelo código."""
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM eap_node WHERE parent_id = ? ORDER BY eap_id",
            (parent_id,),
        )
    return [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]


def listar_todos() -> list[dict[str, Any]]:
    """Retorna todos os nós, ordenados por código hierárquico."""
    with _connect() as conn:
        cursor = conn.execute("SELECT * FROM eap_node ORDER BY eap_id")
    return [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]


def _ultimo_segmento(eap_id: str) -> int:
    """Extrai o último segmento numérico de um código '1.2.3' -> 3."""
    if not eap_id:
        return 0
    match = re.search(r"(\d+)\s*$", eap_id)
    return int(match.group(1)) if match else 0


def proximo_eap_id(parent_id: str | None) -> str:
    """Gera o próximo EAP_ID hierárquico."""
    if parent_id is None:
        seq = max((_ultimo_segmento(n["eap_id"]) for n in listar_todos()), default=0) + 1
        return str(seq)

    irmaos = listar_filhos(parent_id)
    proximo_irmao = len(irmaos) + 1
    return f"{parent_id}.{proximo_irmao}"


def inserir_nodo(dados: dict[str, Any]) -> dict[str, Any]:
    """Insere um nó e devolve o registro completo persistido."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO eap_node (
                eap_id, parent_id, nivel, frente_id, local_id,
                tipo_frente, nome, unidade, quantidade
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dados["eap_id"],
                dados.get("parent_id"),
                dados["nivel"],
                dados.get("frente_id"),
                dados.get("local_id"),
                dados.get("tipo_frente"),
                dados["nome"],
                dados.get("unidade"),
                dados.get("quantidade"),
            ),
        )
        conn.commit()
    return buscar_por_eap_id(dados["eap_id"])  # type: ignore[return-value]


def listar_por_tipo_frente(tipo_frente: str) -> list[dict[str, Any]]:
    """Retorna todos os nós que pertencem a um tipo de frente de serviço."""
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM eap_node WHERE tipo_frente = ? ORDER BY eap_id",
            (tipo_frente,),
        )
    return [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]


# ─────────────────────────────────────────────────────────────────────────────
# Árvore e validação
# ─────────────────────────────────────────────────────────────────────────────


def _raizes() -> list[dict[str, Any]]:
    """Todos os nós sem pai (raízes da EAP)."""
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM eap_node WHERE parent_id IS NULL ORDER BY eap_id"
        )
    return [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]


def montar_arvore(eap_id: str | None = None) -> list[dict[str, Any]]:
    """Monta a(s) árvore(s) aninhada(s) e retorna uma lista de raízes.

    Cada raiz carrega seus dados + uma chave ``filhos`` com os sub-nós
    (recursivo). Chamado sem ``eap_id`` devolve todas as raízes da EAP;
    com ``eap_id`` devolve a subárvore enraizada nesse nó (1 elemento).

    Erros (``ValueError``): nó inexistente ou EAP vazia.
    """
    if eap_id:
        raiz = buscar_por_eap_id(eap_id)
        if raiz is None:
            raise ValueError(f"EAP_ID '{eap_id}' não encontrado na árvore")
        roots: Iterable[dict[str, Any]] = [raiz]
    else:
        roots = _raizes()

    if not roots:
        raise ValueError("A EAP está vazia — nenhum nó para exibir.")

    def _montar(nodo: dict[str, Any]) -> dict[str, Any]:
        no = dict(nodo)
        no["filhos"] = [_montar(f) for f in listar_filhos(nodo["eap_id"])]
        return no

    return [_montar(r) for r in roots]


def validar_estrutura() -> dict[str, Any]:
    """Percorre toda a árvore e reporta problemas de integridade.

    Verifica:
      * duplicidade de EAP_ID (EAP_ID repetido em mais de uma linha);
      * nós órfãos (PARENT_ID aponta para um EAP_ID que não existe);
      * NIVEL inconsistente com a posição real na árvore (pai.nivel + 1).
    """
    problemas: list[str] = []
    todos = listar_todos()

    # 1. Duplicidade de EAP_ID.
    vistos: dict[str, int] = {}
    for n in todos:
        vistos[n["eap_id"]] = vistos.get(n["eap_id"], 0) + 1
    for chave, qtd in vistos.items():
        if qtd > 1:
            problemas.append(f"EAP_ID '{chave}' aparece {qtd} vezes (duplicidade)")

    # 2. Órfãos.
    existentes = set(vistos.keys())
    for n in todos:
        pai = n.get("parent_id")
        if pai is not None and pai not in existentes:
            problemas.append(f"Nó '{n['eap_id']}' é órfão: PARENT_ID '{pai}' não existe")

    # 3. NIVEL inconsistente — percorre a árvore real e confere a profundidade.
    def _percorre(nodo: dict[str, Any], nivel_esperado: int) -> None:
        if nodo["nivel"] != nivel_esperado:
            problemas.append(
                f"Nó '{nodo['eap_id']}' tem NIVEL {nodo['nivel']}, "
                f"mas está na posição {nivel_esperado} da árvore"
            )
        for filho in listar_filhos(nodo["eap_id"]):
            _percorre(filho, nivel_esperado + 1)

    for raiz in _raizes():
        _percorre(raiz, 1)

    return {
        "resumo": {
            "total_nos": len(todos),
            "total_problemas": len(problemas),
            "arvore_valida": len(problemas) == 0,
        },
        "problemas": problemas,
    }
