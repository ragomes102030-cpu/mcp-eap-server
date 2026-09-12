"""Conexão (SQLite/Turso), schema e migrações.

Este é o módulo de mais baixo nível do pacote ``models``: define as tabelas,
abre conexões (Turso via ``libsql_client`` quando ``TURSO_URL`` está
configurada, com fallback pro ``sqlite3`` local) e roda as migrações
incrementais no ``init_db()``. Não importa nada dos outros módulos do
pacote — todos os outros (``nodes``, ``projetos``, ``templates``,
``idempotencia``) dependem deste, nunca o contrário.

Dicionário de unidades válidas: m², m³, ml, un, kg, conj, vb, pt.
Quantidades só são permitidas em nós-folha (sem filhos) — ver ``nodes.py``.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "eap.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS eap_node (
    project_id   TEXT NOT NULL,
    eap_id       TEXT NOT NULL,
    uid          TEXT,
    parent_id    TEXT,
    nivel        INTEGER NOT NULL,
    frente_id    TEXT,
    local_id     TEXT,
    tipo_frente  TEXT,
    nome         TEXT NOT NULL,
    unidade      TEXT,
    quantidade   REAL,
    descricao    TEXT,
    criterio_medicao TEXT,
    responsavel  TEXT,
    disciplina   TEXT,
    nao_aplicavel INTEGER,
    motivo_na    TEXT,
    status       TEXT DEFAULT "ativo",
    revisao      INTEGER DEFAULT 0,
    motivo_retrabalho TEXT,
    origem_uid   TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (project_id, eap_id),
    FOREIGN KEY (project_id, parent_id)
        REFERENCES eap_node(project_id, eap_id)
);
CREATE INDEX IF NOT EXISTS ix_eap_node_parent      ON eap_node(parent_id);
CREATE INDEX IF NOT EXISTS ix_eap_node_tipo_frente ON eap_node(tipo_frente);
CREATE INDEX IF NOT EXISTS ix_eap_node_project     ON eap_node(project_id);

CREATE TABLE IF NOT EXISTS eap_project (
    project_id          TEXT PRIMARY KEY,
    nome                TEXT NOT NULL,
    tipo_obra           TEXT,
    area_m2             REAL,
    metodo_construtivo  TEXT,
    regiao              TEXT,
    cliente             TEXT,
    ativo               INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_eap_project_tipo ON eap_project(tipo_obra);

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

CREATE TABLE IF NOT EXISTS eap_id_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT NOT NULL,
    project_id  TEXT NOT NULL,
    eap_id_de   TEXT NOT NULL,
    eap_id_para TEXT,
    motivo      TEXT,
    em          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_history_uid ON eap_id_history(uid);
CREATE INDEX IF NOT EXISTS ix_history_de  ON eap_id_history(eap_id_de);
"""

_TURSO_URL = os.environ.get("TURSO_URL", "")
_TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "")

DEFAULT_PROJECT_ID = "default"

# F1.2 - transição para raiz única por obra (projeto = obra).
# Fechamento da Fase 1 (2026-09-08): o default da flag INVERTOU. Multi-raiz
# agora é PROBLEMA (invalida a árvore) por padrão — rigor permanente após a
# migração de todos os projetos para raiz única. Para diagnosticar dados
# legados, passe strict_single_root=False explicitamente.
STRICT_SINGLE_ROOT = os.environ.get("EAP_STRICT_SINGLE_ROOT", "1").strip().lower() not in {
    "0", "false", "no",
}


def _normalizar_turso_url(url: str) -> str:
    """Turso novos (ex.: *.aws-us-east-1.turso.io) recusam o handshake WebSocket
    do Hrana (400); o transporte HTTP (https://) funciona. Converte o scheme
    ``libsql://``/``ws(s)://`` em ``http(s)://`` para usar HTTP.
    """
    if url.startswith("libsql://"):
        return "https://" + url[len("libsql://"):]
    if url.startswith("wss://"):
        return "https://" + url[len("wss://"):]
    if url.startswith("ws://"):
        return "http://" + url[len("ws://"):]
    return url


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flag(v: Any) -> Any:
    """Converte True/False em 1/0 (mantém None)."""
    if v is None:
        return None
    return 1 if v else 0


def _chave_ordem(eap_id: str) -> tuple[int, ...]:
    """Chave de ordenação natural: '1.10' vem antes de '1.2'? Não — 1.2 < 1.10.

    Divide o código hierárquico em tupla de inteiros para ORDER em Python.
    """
    try:
        return tuple(int(p) for p in eap_id.split(".") if p.strip())
    except ValueError:
        return tuple(0 for _ in eap_id)


def _gerar_uid() -> str:
    """Gera um uid estável (uuid4 hex) — referência externa imutável do nó."""
    return uuid.uuid4().hex


def _to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


def _to_list(rows: list[Any]) -> list[dict[str, Any]]:
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


_turso_client: Any = None


def _get_turso_client() -> Any:
    """ClientSync único (evita vazar uma sessão aiohttp a cada _connect())."""
    global _turso_client
    if _turso_client is None:
        import libsql_client
        # API síncrona (ClientSync): create_client (async, aiohttp) exigiria
        # um event loop rodando, o que quebraria o DAO síncrono deste módulo.
        # ``_normalizar_turso_url`` troca libsql:// por https:// (Turso novos
        # recusam o handshake WebSocket com HTTP 400).
        _turso_client = libsql_client.create_client_sync(
            url=_normalizar_turso_url(_TURSO_URL), auth_token=_TURSO_TOKEN
        )
    return _turso_client


class _TursoConn:
    """Wrapper que emula a API sqlite3 usando libsql_client (Turso)."""

    def __init__(self) -> None:
        self._client = _get_turso_client()

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


def _connect() -> "_TursoConn | Any":
    """Abre conexão: Turso (se configurado) ou sqlite3 local.

    Resolve ``DB_PATH`` via ``from . import DB_PATH`` (não a constante deste
    módulo) de propósito: assim ``monkeypatch.setattr(models, "DB_PATH", ...)``
    nos testes (que altera o atributo do PACOTE) continua isolando o banco
    corretamente, mesmo com a lógica de conexão morando em ``db.py``.
    """
    if _TURSO_URL:
        return _TursoConn()
    import sqlite3
    from . import DB_PATH as _db_path
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# Projeto: helper de baixo nível usado por nodes.inserir_nodo (evita ciclo
# nodes<->projetos: este helper só toca eap_project via SQL cru).
# ─────────────────────────────────────────────────────────────────────────────


def _garantir_projeto(project_id: str, nome: str | None = None) -> None:
    """Garante a linha de metadados do projeto (cria se ainda não existir)."""
    pid = (project_id or "").strip() or DEFAULT_PROJECT_ID
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO eap_project (project_id, nome) VALUES (?, ?)",
            (pid, nome or pid),
        )
        conn.commit()


def _migrar_registrar_projetos() -> None:
    """Registra no ``eap_project`` todos os ``project_id`` já existentes em
    ``eap_node`` (bancos legados / seeds antigos). Idempotente."""
    try:
        with _connect() as conn:
            cursor = conn.execute("SELECT DISTINCT project_id FROM eap_node")
            for r in cursor.fetchall():
                conn.execute(
                    "INSERT OR IGNORE INTO eap_project (project_id, nome) VALUES (?, ?)",
                    (r["project_id"], r["project_id"]),
                )
            conn.commit()
    except Exception:
        # Banco recém-criado / tabela ainda indisponível: nada a registrar.
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Migrações incrementais (idempotentes)
# ─────────────────────────────────────────────────────────────────────────────

_COLUNAS_F13 = ("descricao", "criterio_medicao", "responsavel", "disciplina")
_COLUNAS_F14 = (("nao_aplicavel", "INTEGER"), ("motivo_na", "TEXT"))
_COLUNAS_F16 = (
    ("status", "TEXT"), ("revisao", "INTEGER"),
    ("motivo", "TEXT"), ("origem_uid", "TEXT"),
)


class MigracaoError(RuntimeError):
    """Erro real (não 'coluna já existe') ao aplicar uma migração de schema."""


def _coluna_ja_existe(exc: Exception) -> bool:
    """True só quando a exceção é 'duplicate column name' (SQLite/Turso).

    Qualquer outro erro (permissão, sintaxe, conexão) é re-levantado — não
    fica mais mascarado por um ``except Exception: pass`` genérico.
    """
    msg = str(exc).lower()
    return "duplicate column" in msg or "already exists" in msg


def _alter_table_idempotente(sql: str) -> None:
    """Roda um ``ALTER TABLE ... ADD COLUMN`` tolerando só 'coluna já existe'.

    Qualquer outro erro (ex.: banco sem permissão de escrita, sintaxe errada)
    propaga como ``MigracaoError`` em vez de ser engolido silenciosamente.
    """
    try:
        with _connect() as conn:
            conn.execute(sql)
            conn.commit()
    except Exception as exc:
        if not _coluna_ja_existe(exc):
            raise MigracaoError(f"Falha ao rodar migração {sql!r}: {exc}") from exc


def _migrar_colunas_texto() -> None:
    """Garante colunas de dicionario/dono (F1.3), N/A (F1.4) e retrabalho (F1.6)."""
    for col in _COLUNAS_F13:
        _alter_table_idempotente(f"ALTER TABLE eap_node ADD COLUMN {col} TEXT")
    for col, tipo in _COLUNAS_F14 + _COLUNAS_F16:
        _alter_table_idempotente(f"ALTER TABLE eap_node ADD COLUMN {col} {tipo}")


def _migrar_uid() -> None:
    """Garante a coluna ``uid`` em ``eap_node`` e preenche nulos (idempotente).

    Bancos antigos (pré-uid) ganham uid estável por nó; a partir daí o ``uid``
    nunca muda — ``eap_id`` vira display e ``move`` grava ``eap_id_history``.

    Usa SQL direto (não ``nodes.listar_todos``) de propósito: este módulo não
    importa ``nodes`` para não criar um ciclo de import entre os dois.
    """
    _alter_table_idempotente("ALTER TABLE eap_node ADD COLUMN uid TEXT")

    with _connect() as conn:
        cursor = conn.execute("SELECT project_id, eap_id, uid FROM eap_node")
        pendentes = [r for r in _to_list(cursor.fetchall()) if not r.get("uid")]
    for n in pendentes:
        with _connect() as conn:
            conn.execute(
                "UPDATE eap_node SET uid = ? WHERE project_id = ? AND eap_id = ?",
                (_gerar_uid(), n["project_id"], n["eap_id"]),
            )
            conn.commit()

    try:
        with _connect() as conn:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_eap_node_uid ON eap_node(uid)"
            )
            conn.commit()
    except Exception as exc:
        if "already exists" not in str(exc).lower():
            raise MigracaoError(f"Falha ao criar índice de uid: {exc}") from exc


def _migrar_eap_node_para_multiprojeto() -> None:
    """Migra ``eap_node`` da PK simples (``eap_id``) para PK composta.

    Aplica-se a bancos SQLite locais. Em Turso (libSQL), a recriação de
    tabela DDL não é feita aqui por segurança: bancos Turso **novos** já usam
    o SCHEMA com PK composta. Se você já tem um database Turso no regime
    antigo (PK simples em ``eap_id``) e precisa de multi-projeto, aplique o
    SCHEMA a PK composta manualmente (CREATE TABLE novo + migração dos dados)
    antes do deploy. Esta função é idempotente.
    """
    import re

    with _connect() as conn:
        if isinstance(conn, _TursoConn):
            return  # Turso/sqld gerencia esse schema; aplica-se manualmente
        cursor = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='eap_node'"
        )
        row = cursor.fetchone()
        if not row:
            return
        sql = row["sql"].strip().lower()
        tem_pk_simples_eap_id = re.search(r"\beap_id\s+text\s+primary\s+key\b", sql)

    if not tem_pk_simples_eap_id:
        return

    # Regime antigo: recria copiando dados, atribuindo DEFAULT_PROJECT_ID.
    with _connect() as conn:
        # Desliga FK temporariamente: a FK composta ainda referencia a tabela
        # antiga (PK simples), o que o SQLite recusa na criação.
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript(
            """
            CREATE TABLE eap_node_novo (
                project_id   TEXT NOT NULL,
                eap_id       TEXT NOT NULL,
                parent_id    TEXT,
                nivel        INTEGER NOT NULL,
                frente_id    TEXT,
                local_id     TEXT,
                tipo_frente  TEXT,
                nome         TEXT NOT NULL,
                unidade      TEXT,
                quantidade   REAL,
                created_at   TEXT DEFAULT (datetime('now')),
                updated_at   TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (project_id, eap_id),
                FOREIGN KEY (project_id, parent_id)
                    REFERENCES eap_node(project_id, eap_id)
            );
            """
        )
        conn.execute(
            f"""
            INSERT INTO eap_node_novo (
                project_id, eap_id, parent_id, nivel, frente_id, local_id,
                tipo_frente, nome, unidade, quantidade, created_at, updated_at
            )
            SELECT '{DEFAULT_PROJECT_ID}', eap_id, parent_id, nivel, frente_id,
                   local_id, tipo_frente, nome, unidade, quantidade,
                   created_at, updated_at
            FROM eap_node
            """
        )
        conn.execute("DROP TABLE eap_node")
        conn.execute("ALTER TABLE eap_node_novo RENAME TO eap_node")
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS ix_eap_node_parent ON eap_node(parent_id);
            CREATE INDEX IF NOT EXISTS ix_eap_node_tipo_frente ON eap_node(tipo_frente);
            CREATE INDEX IF NOT EXISTS ix_eap_node_project ON eap_node(project_id);
            """
        )
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")


def init_db() -> None:
    """Cria as tabelas caso ainda não existam e roda as migrações incrementais."""
    with _connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
    _migrar_eap_node_para_multiprojeto()
    _migrar_registrar_projetos()
    _migrar_uid()
    _migrar_colunas_texto()
