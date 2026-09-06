"""Camada de dados SQLite/libSQL para a EAP (Work Breakdown Structure) de obras.

Usa ``libsql_client`` (Turso) em produção quando ``TURSO_URL`` está configurada,
com fallback pro ``sqlite3`` local para desenvolvimento. Toda a lógica de acesso
a dados, a geração dos códigos hierárquicos (``EAP_ID`` no formato "1.2.3"), o
cálculo do nível e a validação de integridade da árvore vivem aqui.

Tabelas:
  - eap_node: nós da EAP (fiel ao sistema ARES + project_id, timestamps)
  - eap_template_real: 100+ exemplos reais de EAP por tipo de obra
  - eap_idempotency: controle de idempotência (request_id → resposta)

Dicionário de unidades válidas: m², m³, ml, un, kg, conj, vb, pt.
Quantidades só são permitidas em nós-folha (sem filhos).
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DB_PATH = Path(__file__).resolve().parent / "eap.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS eap_node (
    eap_id       TEXT PRIMARY KEY,
    parent_id    TEXT REFERENCES eap_node(eap_id) ON DELETE SET NULL,
    nivel        INTEGER NOT NULL,
    project_id   TEXT,
    frente_id    TEXT,
    local_id     TEXT,
    tipo_frente  TEXT,
    nome         TEXT NOT NULL,
    unidade      TEXT,
    quantidade   REAL,
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_eap_node_parent      ON eap_node(parent_id);
CREATE INDEX IF NOT EXISTS ix_eap_node_tipo_frente ON eap_node(tipo_frente);
CREATE INDEX IF NOT EXISTS ix_eap_node_project     ON eap_node(project_id);

CREATE TABLE IF NOT EXISTS eap_template_real (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    projeto_tipo    TEXT NOT NULL,
    area_m2_min      REAL,
    area_m2_max      REAL,
    metodo_construtivo TEXT,
    regiao          TEXT,
    eap_node        TEXT NOT NULL,
    nome            TEXT NOT NULL,
    unidade         TEXT NOT NULL,
    quantidade_media REAL,
    desvio_padrao   REAL,
    produtividade   TEXT,
    fonte           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_template_tipo    ON eap_template_real(projeto_tipo);
CREATE INDEX IF NOT EXISTS ix_template_area    ON eap_template_real(area_m2_min, area_m2_max);
CREATE INDEX IF NOT EXISTS ix_template_metodo  ON eap_template_real(metodo_construtivo);

CREATE TABLE IF NOT EXISTS eap_idempotency (
    request_id      TEXT PRIMARY KEY,
    tool_name       TEXT NOT NULL,
    payload         TEXT NOT NULL,
    response        TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now'))
);
"""

UNIDADES_VALIDAS = {"m²", "m³", "ml", "un", "kg", "conj", "vb", "pt"}

_NORMALIZACAO_UNIDADES = {
    "m2": "m²", "m3": "m³", "m²": "m²", "m³": "m³",
    "ml": "ml", "un": "un", "kg": "kg", "conj": "conj", "vb": "vb", "pt": "pt",
}

_TURSO_URL = os.environ.get("TURSO_URL", "")
_TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "")

DEFAULT_PROJECT_ID = "default"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalizar_unidade(unidade: str | None) -> str | None:
    """Normaliza unidade pro dicionário válido. Retorna None se inválida."""
    if not unidade:
        return None
    unidade = unidade.strip().lower()
    normalizada = _NORMALIZACAO_UNIDADES.get(unidade)
    if normalizada is None:
        raise ValueError(
            f"Unidade '{unidade}' não reconhecida. Válidas: {', '.join(sorted(UNIDADES_VALIDAS))}"
        )
    return normalizada


def validar_quantidade_so_em_folha(eap_id: str | None, quantidade: float | None) -> None:
    """Quantidades só em nós-folha. Se tem filhos, quantidade deve ser None."""
    if quantidade is None or quantidade == 0:
        return
    filhos = listar_filhos(eap_id) if eap_id else []
    if filhos:
        raise ValueError(
            f"Quantidade só permitida em nós-folha. "
            f"Nó '{eap_id}' tem {len(filhos)} filho(s). "
            f"Remova a quantidade ou crie um filho para ela."
        )


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
    """Cria as tabelas caso ainda não existam."""
    with _connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de row
# ─────────────────────────────────────────────────────────────────────────────


def _to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


def _to_list(rows: list[Any]) -> list[dict[str, Any]]:
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Idempotência
# ─────────────────────────────────────────────────────────────────────────────


def _verificar_idempotencia(request_id: str) -> dict[str, Any] | None:
    """Verifica se request_id já foi processado. Retorna resposta cacheada."""
    if not request_id:
        return None
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT response FROM eap_idempotency WHERE request_id = ?",
            (request_id,),
        )
    row = cursor.fetchone()
    if row:
        import json
        return json.loads(row["response"])
    return None


def _salvar_idempotencia(request_id: str, tool_name: str, payload: Any, response: Any) -> None:
    """Salva resposta pra idempotência."""
    if not request_id:
        return
    import json
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO eap_idempotency (request_id, tool_name, payload, response)
            VALUES (?, ?, ?, ?)
            """,
            (request_id, tool_name, json.dumps(payload), json.dumps(response)),
        )
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


def listar_todos(project_id: str | None = None) -> list[dict[str, Any]]:
    """Retorna todos os nós, ordenados por código hierárquico. Filtra por project_id se informado."""
    if project_id:
        with _connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM eap_node WHERE project_id = ? ORDER BY eap_id",
                (project_id,),
            )
    else:
        with _connect() as conn:
            cursor = conn.execute("SELECT * FROM eap_node ORDER BY eap_id")
    return [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]


def _ultimo_segmento(eap_id: str) -> int:
    """Extrai o último segmento numérico de um código '1.2.3' -> 3."""
    if not eap_id:
        return 0
    match = re.search(r"(\d+)\s*$", eap_id)
    return int(match.group(1)) if match else 0


def proximo_eap_id(parent_id: str | None, project_id: str = DEFAULT_PROJECT_ID) -> str:
    """Gera o próximo EAP_ID hierárquico."""
    if parent_id is None:
        with _connect() as conn:
            cursor = conn.execute(
                "SELECT eap_id FROM eap_node WHERE project_id = ?",
                (project_id,),
            )
        rows = cursor.fetchall()
        seq = max((_ultimo_segmento(r["eap_id"]) for r in rows), default=0) + 1
        return str(seq)

    irmaos = listar_filhos(parent_id)
    proximo_irmao = len(irmaos) + 1
    return f"{parent_id}.{proximo_irmao}"


def inserir_nodo(dados: dict[str, Any]) -> dict[str, Any]:
    """Insere um nó e devolve o registro completo persistido."""
    unidade = normalizar_unidade(dados.get("unidade"))
    quantidade = dados.get("quantidade")

    validar_quantidade_so_em_folha(None, quantidade)

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO eap_node (
                eap_id, parent_id, nivel, project_id, frente_id, local_id,
                tipo_frente, nome, unidade, quantidade, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dados["eap_id"],
                dados.get("parent_id"),
                dados["nivel"],
                dados.get("project_id", DEFAULT_PROJECT_ID),
                dados.get("frente_id"),
                dados.get("local_id"),
                dados.get("tipo_frente"),
                dados["nome"],
                unidade,
                quantidade,
                _agora_iso(),
                _agora_iso(),
            ),
        )
        conn.commit()
    return buscar_por_eap_id(dados["eap_id"])  # type: ignore[return-value]


def atualizar_nodo(eap_id: str, dados: dict[str, Any]) -> dict[str, Any]:
    """Atualiza campos de um nó existente."""
    existente = buscar_por_eap_id(eap_id)
    if existente is None:
        raise ValueError(f"EAP_ID '{eap_id}' não encontrado")

    unidade = normalizar_unidade(dados.get("unidade")) if "unidade" in dados else None
    quantidade = dados.get("quantidade") if "quantidade" in dados else None

    validar_quantidade_so_em_folha(eap_id, quantidade)

    campos = []
    valores = []
    for campo in ["frente_id", "local_id", "tipo_frente", "nome"]:
        if campo in dados:
            campos.append(f"{campo} = ?")
            valores.append(dados[campo])
    if unidade is not None:
        campos.append("unidade = ?")
        valores.append(unidade)
    if quantidade is not None:
        campos.append("quantidade = ?")
        valores.append(quantidade)

    if not campos:
        return existente

    campos.append("updated_at = ?")
    valores.append(_agora_iso())
    valores.append(eap_id)

    with _connect() as conn:
        conn.execute(
            f"UPDATE eap_node SET {', '.join(campos)} WHERE eap_id = ?",
            tuple(valores),
        )
        conn.commit()
    return buscar_por_eap_id(eap_id)  # type: ignore[return-value]


def deletar_nodo(eap_id: str, cascade: bool = False) -> dict[str, Any]:
    """Deleta um nó. Se cascade=True, deleta todos os descendentes."""
    existente = buscar_por_eap_id(eap_id)
    if existente is None:
        raise ValueError(f"EAP_ID '{eap_id}' não encontrado")

    if cascade:
        for filho in listar_filhos(eap_id):
            deletar_nodo(filho["eap_id"], cascade=True)
    else:
        filhos = listar_filhos(eap_id)
        if filhos:
            raise ValueError(
                f"Nó '{eap_id}' tem {len(filhos)} filho(s). "
                f"Use cascade=True para deletar com descendentes."
            )

    with _connect() as conn:
        conn.execute("DELETE FROM eap_node WHERE eap_id = ?", (eap_id,))
        conn.commit()
    return {"deletado": True, "eap_id": eap_id}


def deletar_projeto(project_id: str) -> dict[str, Any]:
    """Deleta todos os nós de um projeto."""
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) AS n FROM eap_node WHERE project_id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        total = row["n"] if row else 0
        conn.execute("DELETE FROM eap_node WHERE project_id = ?", (project_id,))
        conn.commit()
    return {"deletado": True, "project_id": project_id, "total_nos": total}


def listar_projetos() -> list[dict[str, Any]]:
    """Lista todos os projetos com contagem de nós."""
    with _connect() as conn:
        cursor = conn.execute(
            """
            SELECT project_id, COUNT(*) AS total_nos, MIN(created_at) AS criado_em
            FROM eap_node
            GROUP BY project_id
            ORDER BY project_id
            """
        )
    return cursor.fetchall()


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


# ─────────────────────────────────────────────────────────────────────────────
# Templates reais (exemplos históricos de EAP)
# ─────────────────────────────────────────────────────────────────────────────


def inserir_template(dados: dict[str, Any]) -> dict[str, Any]:
    """Insere um exemplo real de EAP."""
    unidade = normalizar_unidade(dados["unidade"])
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO eap_template_real (
                projeto_tipo, area_m2_min, area_m2_max, metodo_construtivo,
                regiao, eap_node, nome, unidade, quantidade_media,
                desvio_padrao, produtividade, fonte
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dados["projeto_tipo"],
                dados.get("area_m2_min"),
                dados.get("area_m2_max"),
                dados.get("metodo_construtivo"),
                dados.get("regiao"),
                dados["eap_node"],
                dados["nome"],
                unidade,
                dados.get("quantidade_media"),
                dados.get("desvio_padrao"),
                dados.get("produtividade"),
                dados.get("fonte"),
            ),
        )
        conn.commit()
    return {"inserido": True}


def listar_templates(
    projeto_tipo: str | None = None,
    area_m2: float | None = None,
    metodo_construtivo: str | None = None,
) -> list[dict[str, Any]]:
    """Lista templates com filtros opcionais."""
    where = []
    params = []
    if projeto_tipo:
        where.append("projeto_tipo = ?")
        params.append(projeto_tipo)
    if area_m2 is not None:
        where.append("(area_m2_min <= ? OR area_m2_min IS NULL)")
        params.append(area_m2)
        where.append("(area_m2_max >= ? OR area_m2_max IS NULL)")
        params.append(area_m2)
    if metodo_construtivo:
        where.append("metodo_construtivo = ?")
        params.append(metodo_construtivo)

    sql = "SELECT * FROM eap_template_real"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY projeto_tipo, eap_node"

    with _connect() as conn:
        cursor = conn.execute(sql, tuple(params))
    return cursor.fetchall()


def contar_templates() -> int:
    """Retorna total de templates cadastrados."""
    with _connect() as conn:
        cursor = conn.execute("SELECT COUNT(*) AS n FROM eap_template_real")
        row = cursor.fetchone()
    return row["n"] if row else 0
