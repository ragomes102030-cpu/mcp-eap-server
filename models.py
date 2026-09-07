"""Camada de dados SQLite/libSQL para a EAP (Work Breakdown Structure) de obras.

Usa ``libsql_client`` (Turso) em produção quando ``TURSO_URL`` está configurada,
com fallback pro ``sqlite3`` local para desenvolvimento. Toda a lógica de acesso
a dados, a geração dos códigos hierárquicos (``EAP_ID`` no formato "1.2.3"), o
cálculo do nível e a validação de integridade da árvore vivem aqui.

Tabelas:
  - eap_node: nós da EAP (fiel ao sistema ARES + project_id, timestamps)
  - eap_project: metadados de projetos/obras (nome, tipo_obra, área, método, região, cliente)
  - eap_template_real: 100+ exemplos reais de EAP por tipo de obra
  - eap_idempotency: controle de idempotência (request_id → resposta)

Dicionário de unidades válidas: m², m³, ml, un, kg, conj, vb, pt.
Quantidades só são permitidas em nós-folha (sem filhos).
"""

from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DB_PATH = Path(__file__).resolve().parent / "eap.db"

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

UNIDADES_VALIDAS = {"m²", "m³", "ml", "un", "kg", "conj", "vb", "pt"}

_NORMALIZACAO_UNIDADES = {
    "m2": "m²", "m3": "m³", "m²": "m²", "m³": "m³",
    "ml": "ml", "un": "un", "kg": "kg", "conj": "conj", "vb": "vb", "pt": "pt",
}

# Vocabulário fechado de tipos de frente de serviço (obra real). Mantém a
# classificação estável para consultas e relatórios — o LLM não inventa valores.
TIPOS_FRENTE_VALIDOS = {
    "projeto", "preliminares", "fundacao", "estrutura", "alvenaria",
    "cobertura", "eletrica", "hidrossanitaria", "esquadrias",
    "revestimento", "pintura", "acabamento",
    "infraestrutura", "paisagismo",
}

_NORMALIZACAO_TIPOS = {
    "fundações": "fundacao", "fundacao": "fundacao", "fundacoes": "fundacao",
    "estrutura": "estrutura",
    "alvenaria": "alvenaria", "alvenaria_estrutural": "alvenaria",
    "cobertura": "cobertura", "cubierta": "cobertura", "telhado": "cobertura",
    # F1.2/§3: 'instalacoes' foi DEPRECIADO e dividido em eletrica/hidrossanitaria.
    "eletrica": "eletrica", "eletrico": "eletrica", "elétrica": "eletrica",
    "instalacoes_eletricas": "eletrica",
    "hidrossanitaria": "hidrossanitaria", "hidraulica": "hidrossanitaria",
    "hidraulico": "hidrossanitaria", "hidráulica": "hidrossanitaria",
    "instalacoes_hidrossanitarias": "hidrossanitaria",
    "esgoto": "hidrossanitaria", "agua": "hidrossanitaria", "água": "hidrossanitaria",
    "esquadrias": "esquadrias", "esquinerias": "esquadrias", "esquadria": "esquadrias",
    "revestimento": "revestimento",
    "pintura": "pintura",
    "acabamento": "acabamento",
    "infraestrutura": "infraestrutura", "infra": "infraestrutura",
    "paisagismo": "paisagismo",
    "preliminares": "preliminares", "projeto": "projeto",
}


def normalizar_tipo_frente(tipo: str | None) -> str | None:
    """Normaliza um tipo de frente de serviço pro vocabulário fechado.

    Rejeita valores fora do dicionário em vez de gravar dados sujos.
    Retorna None quando o campo está vazio/ausente.
    """
    if not tipo:
        return None
    t = tipo.strip().lower().replace("_", " ")
    # remove acentos: "Instalações Elétricas" -> "instalacoes eletricas"
    t = "".join(ch for ch in unicodedata.normalize("NFD", t)
                if unicodedata.category(ch) != "Mn").strip()
    # tenta primeiro o valor canônico, depois os sinônimos normalizados
    if t.replace(" ", "_") in TIPOS_FRENTE_VALIDOS:
        return t.replace(" ", "_")
    normalizado = _NORMALIZACAO_TIPOS.get(t) or _NORMALIZACAO_TIPOS.get(t.replace(" ", "_"))
    if normalizado is not None:
        return normalizado
    if t.replace(" ", "_") == "instalacoes":
        raise ValueError(
            "Tipo de frente 'instalacoes' foi DEPRECIADO e dividido em "
            "'eletrica' e 'hidrossanitaria' (informe um deles)."
        )
    raise ValueError(
        f"Tipo de frente '{tipo}' não reconhecido. "
        f"Válidos: {', '.join(sorted(TIPOS_FRENTE_VALIDOS))}"
    )


def _chave_ordem(eap_id: str) -> tuple[int, ...]:
    """Chave de ordenação natural: '1.10' vem antes de '1.2'? Não — 1.2 < 1.10.

    Divide o código hierárquico em tupla de inteiros para ORDER em Python.
    """
    try:
        return tuple(int(p) for p in eap_id.split(".") if p.strip())
    except ValueError:
        return tuple(0 for _ in eap_id)

_TURSO_URL = os.environ.get("TURSO_URL", "")
_TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "")

DEFAULT_PROJECT_ID = "default"

# F1.2 - transição para raiz única por obra (projeto = obra).
# Começa DESLIGADA: validar mantém multi-raiz como aviso. Ligue (env
# EAP_STRICT_SINGLE_ROOT=1) SOMENTE depois de migrar os projetos para raiz única.
STRICT_SINGLE_ROOT = os.environ.get("EAP_STRICT_SINGLE_ROOT", "").strip().lower() in {
    "1", "true", "yes",
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


def validar_quantidade_so_em_folha(
    eap_id: str | None,
    quantidade: float | None,
    project_id: str | None = None,
) -> None:
    """Quantidades só em nós-folha. Se tem filhos, quantidade deve ser None."""
    if quantidade is None or quantidade == 0:
        return
    filhos = listar_filhos(eap_id, project_id) if eap_id else []
    if filhos:
        raise ValueError(
            f"Quantidade só permitida em nós-folha. "
            f"Nó '{eap_id}' tem {len(filhos)} filho(s). "
            f"Remova a quantidade ou crie um filho para ela."
        )


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
    _migrar_eap_node_para_multiprojeto()
    _migrar_registrar_projetos()
    _migrar_uid()
    _migrar_colunas_texto()


def _migrar_eap_node_para_multiprojeto() -> None:
    """Migra ``eap_node`` da PK simples (``eap_id``) para PK composta.

    Aplica-se a bancos SQLite locais. Em Turso (libSQL), a recriação de
    tabela DDL não é feita aqui por segurança: bancos Turso **novos** já usam
    o SCHEMA com PK composta. Se você já tem um database Turso no regime
    antigo (PK simples em ``eap_id``) e precisa de multi-projeto, aplique o
    SCHEMA a PK composta manualmente (CREATE TABLE novo + migração dos dados)
    antes do deploy. Esta função é idempotente.
    """
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
    if tem_pk_simples_eap_id:
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
                CREATE INDEX IF NOT EXISTS ix_eap_node_parent      ON eap_node(parent_id);
                CREATE INDEX IF NOT EXISTS ix_eap_node_tipo_frente ON eap_node(tipo_frente);
                CREATE INDEX IF NOT EXISTS ix_eap_node_project     ON eap_node(project_id);
                """
            )
            conn.commit()
            conn.execute("PRAGMA foreign_keys = ON")


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


def verificar_idempotencia(request_id: str) -> dict[str, Any] | None:
    """API pública: retorna a resposta cacheada p/ um request_id, ou None."""
    return _verificar_idempotencia(request_id)


def salvar_idempotencia(
    request_id: str, tool_name: str, payload: Any, response: Any
) -> None:
    """API pública: salva a resposta p/ idempotência."""
    _salvar_idempotencia(request_id, tool_name, payload, response)


def limpar_idempotencia_antiga(horas: int = 24) -> int:
    """Remove registros de idempotência mais velhos que ``horas``. Retorna nº removido."""
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM eap_idempotency WHERE created_at < datetime('now', ?)",
            (f"-{horas} hours",),
        )
        conn.commit()
    # fetch via count para evitar leak de cursor fora do with
    removidos = 0
    if hasattr(cursor, "rowcount") and cursor.rowcount and cursor.rowcount > 0:
        removidos = int(cursor.rowcount)
    return removidos


# ─────────────────────────────────────────────────────────────────────────────
# DAO básico
# ─────────────────────────────────────────────────────────────────────────────


_PROJETO_CAMPOS = (
    "project_id, nome, tipo_obra, area_m2, metodo_construtivo, regiao, "
    "cliente, ativo, created_at, updated_at"
)


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


def buscar_projeto(project_id: str) -> dict[str, Any] | None:
    """Retorna os metadados de um projeto, ou None se não existir."""
    with _connect() as conn:
        cursor = conn.execute(
            f"SELECT {_PROJETO_CAMPOS} FROM eap_project WHERE project_id = ?",
            (project_id,),
        )
    return _to_dict(cursor.fetchone())


def criar_projeto(
    project_id: str,
    nome: str | None = None,
    tipo_obra: str | None = None,
    area_m2: float | None = None,
    metodo_construtivo: str | None = None,
    regiao: str | None = None,
    cliente: str | None = None,
) -> dict[str, Any]:
    """Cria os metadados de um novo projeto (obra). Erro se já existir."""
    pid = (project_id or "").strip()
    if not pid:
        raise ValueError("project_id é obrigatório e não pode ser vazio.")
    if buscar_projeto(pid) is not None:
        raise ValueError(f"Projeto '{pid}' já existe.")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO eap_project (
                project_id, nome, tipo_obra, area_m2, metodo_construtivo,
                regiao, cliente
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (pid, nome or pid, tipo_obra, area_m2, metodo_construtivo, regiao, cliente),
        )
        conn.commit()
    return buscar_projeto(pid)  # type: ignore[return-value]


def atualizar_projeto(project_id: str, **campos: Any) -> dict[str, Any]:
    """Atualiza campos opcionais dos metadados de um projeto existente."""
    permitidos = {
        "nome", "tipo_obra", "area_m2", "metodo_construtivo",
        "regiao", "cliente", "ativo",
    }
    dados = {k: v for k, v in campos.items() if k in permitidos and v is not None}
    if not dados:
        raise ValueError("Nenhum campo válido para atualizar o projeto.")
    if buscar_projeto(project_id) is None:
        raise ValueError(f"Projeto '{project_id}' não existe.")
    pares = ", ".join(f"{c} = ?" for c in dados)
    valores = [*dados.values(), project_id]
    with _connect() as conn:
        conn.execute(
            f"UPDATE eap_project SET {pares}, updated_at = datetime('now') "
            "WHERE project_id = ?",
            tuple(valores),
        )
        conn.commit()
    return buscar_projeto(project_id)  # type: ignore[return-value]


def listar_projetos() -> list[dict[str, Any]]:
    """Lista todos os projetos com metadados e a contagem de nós (0 se vazio)."""
    with _connect() as conn:
        cursor = conn.execute(
            """
            SELECT p.project_id, p.nome, p.tipo_obra, p.area_m2,
                   p.metodo_construtivo, p.regiao, p.cliente, p.ativo,
                   p.created_at, p.updated_at,
                   COUNT(n.project_id) AS total_nos
            FROM eap_project p
            LEFT JOIN eap_node n ON n.project_id = p.project_id
            GROUP BY p.project_id
            ORDER BY p.project_id
            """
        )
    return [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]


def deletar_projeto(project_id: str) -> dict[str, Any]:
    """Deleta todos os nós e os metadados de um projeto."""
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) AS n FROM eap_node WHERE project_id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        total = row["n"] if row else 0
        conn.execute("DELETE FROM eap_node WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM eap_project WHERE project_id = ?", (project_id,))
        conn.commit()
    return {"deletado": True, "project_id": project_id, "total_nos": total}


def _gerar_uid() -> str:
    """Gera um uid estável (uuid4 hex) — referência externa imutável do nó."""
    return uuid.uuid4().hex


def buscar_por_uid(uid: str, project_id: str | None = None) -> dict[str, Any] | None:
    """Retorna um nó pelo ``uid`` estável. Sem projeto, assume o default."""
    pid = project_id if project_id is not None else DEFAULT_PROJECT_ID
    if not uid:
        return None
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM eap_node WHERE uid = ? AND project_id = ?",
            (uid, pid),
        )
    return _to_dict(cursor.fetchone())


def historico_movimentos(
    project_id: str | None = None,
    uid: str | None = None,
    eap_id_de: str | None = None,
    limite: int = 500,
) -> list[dict[str, Any]]:
    """Histórico de renumeracão (EAP_ID display) de nós movidos.

    ``uid`` é estável; ``eap_id`` é display e muda a cada ``move``. A tabela
    permite resolver ``eap_id`` antigo -> nó atual (auditoria / movido_para).
    """
    where: list[str] = []
    params: list[Any] = []
    if project_id:
        where.append("project_id = ?")
        params.append(project_id)
    if uid:
        where.append("uid = ?")
        params.append(uid)
    if eap_id_de:
        where.append("eap_id_de = ?")
        params.append(eap_id_de)
    sql = "SELECT * FROM eap_id_history"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limite))
    with _connect() as conn:
        cursor = conn.execute(sql, tuple(params))
    return _to_list(cursor.fetchall())


def _migrar_uid() -> None:
    """Garante a coluna ``uid`` em ``eap_node`` e preenche nulos (idempotente).

    Bancos antigos (pré-uid) ganham uid estável por nó; a partir daí o ``uid``
    nunca muda — ``eap_id`` vira display e ``move`` grava ``eap_id_history``.
    """
    try:
        with _connect() as conn:
            conn.execute("ALTER TABLE eap_node ADD COLUMN uid TEXT")
            conn.commit()
    except Exception:
        pass  # coluna já existe
    pendentes = [n for n in listar_todos() if not n.get("uid")]
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
    except Exception:
        pass


_COLUNAS_F13 = ("descricao", "criterio_medicao", "responsavel", "disciplina")


def _migrar_colunas_texto() -> None:
    """Garante as colunas de dicionario/dono (F1.3) em ``eap_node`` (idempotente)."""
    for col in _COLUNAS_F13:
        try:
            with _connect() as conn:
                conn.execute(f"ALTER TABLE eap_node ADD COLUMN {col} TEXT")
                conn.commit()
        except Exception:
            pass  # coluna ja existe


def buscar_por_eap_id(
    eap_id: str, project_id: str | None = None
) -> dict[str, Any] | None:
    """Retorna um nó pelo EAP_ID dentro do projeto. Sem projeto, usa o default."""
    pid = project_id if project_id is not None else DEFAULT_PROJECT_ID
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM eap_node WHERE eap_id = ? AND project_id = ?",
            (eap_id, pid),
        )
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


def listar_filhos(
    parent_id: str, project_id: str | None = None
) -> list[dict[str, Any]]:
    """Retorna os filhos diretos de um nó, ordenados pelo código hierárquico.

    Sem ``project_id`` explícito, assume o projeto default (nunca mistura
    projetos na consulta de subárvore)."""
    pid = project_id if project_id is not None else DEFAULT_PROJECT_ID
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM eap_node WHERE parent_id = ? AND project_id = ?",
            (parent_id, pid),
        )
    rows = [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]
    rows.sort(key=lambda n: _chave_ordem(n["eap_id"]))
    return rows


def listar_todos(project_id: str | None = None) -> list[dict[str, Any]]:
    """Retorna todos os nós, ordenados pelo código hierárquico. Filtra por project_id se informado."""
    if project_id:
        with _connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM eap_node WHERE project_id = ?",
                (project_id,),
            )
    else:
        with _connect() as conn:
            cursor = conn.execute("SELECT * FROM eap_node")
    rows = [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]
    rows.sort(key=lambda n: _chave_ordem(n["eap_id"]))
    return rows


def listar_pacotes_sem_dono(
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Folhas (itens mensuráveis) ainda sem ``responsavel`` definido (OBS)."""
    todos = listar_todos(project_id)
    sao_pais = {n["parent_id"] for n in todos if n.get("parent_id") is not None}
    folhas = [n for n in todos if n["eap_id"] not in sao_pais]
    sem_dono = [
        n for n in folhas
        if not (n.get("responsavel") or "").strip()
    ]
    sem_dono.sort(key=lambda n: _chave_ordem(n["eap_id"]))
    return sem_dono


def _ultimo_segmento(eap_id: str) -> int:
    """Extrai o último segmento numérico de um código '1.2.3' -> 3."""
    if not eap_id:
        return 0
    match = re.search(r"(\d+)\s*$", eap_id)
    return int(match.group(1)) if match else 0


def proximo_eap_id(parent_id: str | None, project_id: str = DEFAULT_PROJECT_ID) -> str:
    """Gera o próximo EAP_ID hierárquico (sem reutilizar códigos deletados)."""
    if parent_id is None:
        with _connect() as conn:
            cursor = conn.execute(
                "SELECT eap_id FROM eap_node WHERE project_id = ?",
                (project_id,),
            )
        rows = cursor.fetchall()
        seq = max((_ultimo_segmento(r["eap_id"]) for r in rows), default=0) + 1
        return str(seq)

    irmaos = listar_filhos(parent_id, project_id)
    if irmaos:
        ultimo = max(_ultimo_segmento(r["eap_id"]) for r in irmaos)
        proximo_irmao = ultimo + 1
    else:
        proximo_irmao = 1
    return f"{parent_id}.{proximo_irmao}"


def inserir_nodo(dados: dict[str, Any]) -> dict[str, Any]:
    """Insere um nó e devolve o registro completo persistido."""
    uid = dados.get("uid") or _gerar_uid()
    unidade = normalizar_unidade(dados.get("unidade"))
    quantidade = dados.get("quantidade")
    project_id = dados.get("project_id", DEFAULT_PROJECT_ID)
    _garantir_projeto(project_id)
    tipo_frente = normalizar_tipo_frente(dados.get("tipo_frente"))

    # Validação referencial: mãe precisa existir no mesmo projeto.
    if dados.get("parent_id") is not None:
        pai = buscar_por_eap_id(dados["parent_id"], project_id)
        if pai is None:
            raise ValueError(
                f"PARENT_ID '{dados['parent_id']}' não existe no projeto '{project_id}'."
            )

    validar_quantidade_so_em_folha(None, quantidade, project_id)

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO eap_node (
                uid, eap_id, parent_id, nivel, project_id, frente_id, local_id,
                tipo_frente, nome, unidade, quantidade,
                descricao, criterio_medicao, responsavel, disciplina,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uid,
                dados["eap_id"],
                dados.get("parent_id"),
                dados["nivel"],
                project_id,
                dados.get("frente_id"),
                dados.get("local_id"),
                tipo_frente,
                dados["nome"],
                unidade,
                quantidade,
                dados.get("descricao"),
                dados.get("criterio_medicao"),
                dados.get("responsavel"),
                dados.get("disciplina"),
                _agora_iso(),
                _agora_iso(),
            ),
        )
        conn.commit()
    return buscar_por_eap_id(dados["eap_id"], project_id)  # type: ignore[return-value]


def atualizar_nodo(eap_id: str, dados: dict[str, Any]) -> dict[str, Any]:
    """Atualiza campos de um nó existente."""
    project_id = dados.pop("project_id", DEFAULT_PROJECT_ID)
    existente = buscar_por_eap_id(eap_id, project_id)
    if existente is None:
        raise ValueError(f"EAP_ID '{eap_id}' não encontrado no projeto '{project_id}'")

    if "unidade" in dados:
        normalizar_unidade(dados.get("unidade"))
    unidade = normalizar_unidade(dados.get("unidade")) if "unidade" in dados else None
    quantidade = dados.get("quantidade") if "quantidade" in dados else None
    if "tipo_frente" in dados:
        dados["tipo_frente"] = normalizar_tipo_frente(dados.get("tipo_frente"))

    validar_quantidade_so_em_folha(eap_id, quantidade, project_id)

    campos = []
    valores = []
    for campo in ["frente_id", "local_id", "tipo_frente", "nome",
                  "descricao", "criterio_medicao", "responsavel", "disciplina"]:
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
            f"UPDATE eap_node SET {', '.join(campos)} WHERE eap_id = ? AND project_id = ?",
            tuple(valores[:]) + (project_id,),
        )
        conn.commit()
    return buscar_por_eap_id(eap_id, project_id)  # type: ignore[return-value]


def deletar_nodo(
    eap_id: str,
    cascade: bool = False,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Deleta um nó. Se cascade=True, deleta todos os descendentes."""
    if project_id is None:
        project_id = DEFAULT_PROJECT_ID
    existente = buscar_por_eap_id(eap_id, project_id)
    if existente is None:
        raise ValueError(f"EAP_ID '{eap_id}' não encontrado no projeto '{project_id}'")

    if cascade:
        for filho in listar_filhos(eap_id, project_id):
            deletar_nodo(filho["eap_id"], cascade=True, project_id=project_id)
    else:
        filhos = listar_filhos(eap_id, project_id)
        if filhos:
            raise ValueError(
                f"Nó '{eap_id}' tem {len(filhos)} filho(s). "
                f"Use cascade=True para deletar com descendentes."
            )

    with _connect() as conn:
        conn.execute(
            "DELETE FROM eap_node WHERE eap_id = ? AND project_id = ?",
            (eap_id, project_id),
        )
        conn.commit()
    return {"deletado": True, "eap_id": eap_id, "project_id": project_id}








def listar_por_tipo_frente(
    tipo_frente: str,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Retorna todos os nós que pertencem a um tipo de frente de serviço.

    Sem ``project_id`` explícito, assume o projeto default."""
    pid = project_id if project_id is not None else DEFAULT_PROJECT_ID
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT * FROM eap_node WHERE tipo_frente = ? AND project_id = ?",
            (tipo_frente, pid),
        )
    rows = [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]
    rows.sort(key=lambda n: _chave_ordem(n["eap_id"]))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Árvore e validação
# ─────────────────────────────────────────────────────────────────────────────


def _raizes(project_id: str | None = None) -> list[dict[str, Any]]:
    """Todos os nós sem pai (raízes da EAP), opcionalmente por projeto."""
    if project_id:
        with _connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM eap_node WHERE parent_id IS NULL AND project_id = ?",
                (project_id,),
            )
    else:
        with _connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM eap_node WHERE parent_id IS NULL"
            )
    rows = [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]
    rows.sort(key=lambda n: _chave_ordem(n["eap_id"]))
    return rows


def montar_arvore(
    eap_id: str | None = None,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Monta a(s) árvore(s) aninhada(s) e retorna uma lista de raízes.

    Cada raiz carrega seus dados + uma chave ``filhos`` com os sub-nós
    (recursivo). Chamado sem ``eap_id`` devolve todas as raízes do projeto;
    com ``eap_id`` devolve a subárvore enraizada nesse nó (1 elemento).

    Erros (``ValueError``): nó inexistente ou EAP vazia.
    """
    if eap_id:
        raiz = buscar_por_eap_id(eap_id, project_id)
        if raiz is None:
            raise ValueError(f"EAP_ID '{eap_id}' não encontrado na árvore")
        roots: Iterable[dict[str, Any]] = [raiz]
        scope = raiz.get("project_id") or project_id or DEFAULT_PROJECT_ID
    else:
        roots = _raizes(project_id)
        scope = project_id

    if not roots:
        raise ValueError("A EAP está vazia — nenhum nó para exibir.")

    def _montar(nodo: dict[str, Any]) -> dict[str, Any]:
        no = dict(nodo)
        no["filhos"] = [_montar(f) for f in listar_filhos(nodo["eap_id"], scope)]
        return no

    return [_montar(r) for r in roots]


def mover_nodo(
    eap_id: str,
    novo_parent_id: str | None,
    project_id: str = DEFAULT_PROJECT_ID,
    motivo: str | None = None,
) -> dict[str, Any]:
    """Move um nó (e sua subárvore) para um novo pai.

    ``uid`` é estável e **nunca muda**: apenas ``EAP_ID``/``NIVEL`` são
    recalculados (display). Cada nó movido ganha um registro em
    ``eap_id_history`` (de/para/motivo). Bloqueia movimento que criaria ciclo.
    """
    no = buscar_por_eap_id(eap_id, project_id)
    if no is None:
        raise ValueError(f"EAP_ID '{eap_id}' não encontrado no projeto '{project_id}'")

    if novo_parent_id is not None:
        pai = buscar_por_eap_id(novo_parent_id, project_id)
        if pai is None:
            raise ValueError(
                f"NOVO_PARENT_ID '{novo_parent_id}' não existe no projeto '{project_id}'."
            )
        if novo_parent_id == eap_id:
            raise ValueError("Não é possível mover um nó para ser filho dele mesmo.")
        descendentes = set(_subarvore_ids(eap_id, project_id)) - {eap_id}
        if novo_parent_id in descendentes:
            raise ValueError(
                f"Não é possível mover '{eap_id}' para '{novo_parent_id}': "
                "isso cria um ciclo (o destino é um descendente do nó)."
            )

    sub = _coletar_subarvore(eap_id, project_id)
    return _executar_move(sub, eap_id, novo_parent_id, project_id, motivo)


def _subarvore_ids(eap_id: str, project_id: str) -> list[str]:
    """EAP_IDs da subárvore (eu + descendentes), em ordem."""
    ids: list[str] = []

    def _coleta(nid: str) -> None:
        ids.append(nid)
        for f in listar_filhos(nid, project_id):
            _coleta(f["eap_id"])

    _coleta(eap_id)
    return ids


def _coletar_subarvore(
    eap_id: str, project_id: str
) -> list[dict[str, Any]]:
    """Lista de {eap_id, parent_id, nivel, dados} da subárvore."""
    from collections import deque

    out: list[dict[str, Any]] = []
    raiz = buscar_por_eap_id(eap_id, project_id)
    if raiz is None:
        return out

    # BFS para coletar os nós com seus pais originais
    fila: deque[dict[str, Any]] = deque([raiz])
    while fila:
        n = fila.popleft()
        out.append(
            {
                "eap_id": n["eap_id"],
                "parent_id": n["parent_id"],
                "nivel": n["nivel"],
                "dados": n,
            }
        )
        for f in listar_filhos(n["eap_id"], project_id):
            fila.append(f)
    return out


def _executar_move(
    sub: list[dict[str, Any]],
    eap_id: str,
    novo_parent_id: str | None,
    project_id: str,
    motivo: str | None = None,
) -> dict[str, Any]:
    """Reinsere a subárvore re-numerada sob o novo pai, atomicamente.

    Preserva o ``uid`` de cada nó (referência estável) e grava ``eap_id_history``
    com o mapeamento de/para de cada nó movido (auditoria de renumeração).
    """
    raiz_antigo = eap_id

    # Novo código e nível da raiz movida.
    if novo_parent_id is None:
        tops = [r["eap_id"] for r in _raizes(project_id)]
        seg = max((_ultimo_segmento(s) for s in tops), default=0) + 1
        novo_codigo_raiz = str(seg)
        novo_nivel = 1
    else:
        irmaos = listar_filhos(novo_parent_id, project_id)
        seg = max((_ultimo_segmento(f["eap_id"]) for f in irmaos), default=0) + 1
        novo_codigo_raiz = f"{novo_parent_id}.{seg}"
        pai_alvo = buscar_por_eap_id(novo_parent_id, project_id)
        novo_nivel = (pai_alvo["nivel"] + 1) if pai_alvo else 1

    # Próximos códigos por BFS usando os parent_id antigos.
    novo_id: dict[str, str] = {raiz_antigo: novo_codigo_raiz}
    nivel_novo: dict[str, int] = {raiz_antigo: novo_nivel}
    filhos_por_pai: dict[str, list[dict[str, Any]]] = {}
    for n in sub:
        filhos_por_pai.setdefault(n["parent_id"], []).append(n)
    for k in filhos_por_pai:
        filhos_por_pai[k].sort(key=lambda x: _chave_ordem(x["eap_id"]))

    from collections import deque

    fila: deque[str] = deque([raiz_antigo])
    while fila:
        atual = fila.popleft()
        novo_pai_cod = novo_id[atual]
        nivel_atual = nivel_novo[atual]
        seq = 0
        for filho in filhos_por_pai.get(atual, []):
            seq += 1
            novo_id[filho["eap_id"]] = (
                f"{novo_pai_cod}.{seq}" if novo_pai_cod else f"{seq}"
            )
            nivel_novo[filho["eap_id"]] = nivel_atual + 1
            fila.append(filho["eap_id"])

    # parent_id novo (por código novo). A raiz movida recebe o ``novo_parent_id``
    # direto; os descendentes recebem o código novo do pai antigo (já mapeado).
    novo_pai_map: dict[str, str | None] = {}
    for n in sub:
        cod = novo_id[n["eap_id"]]
        if cod == novo_codigo_raiz:
            novo_pai_map[cod] = novo_parent_id
        else:
            antigo_pai = n["parent_id"]
            novo_pai_map[cod] = novo_id.get(antigo_pai)

    # Persistência atômica (deletar antigos + reinserir novos + histórico).
    with _connect() as conn:
        conn.execute(
            "DELETE FROM eap_node WHERE project_id = ? AND eap_id IN ({0})".format(
                ",".join("?" for _ in novo_id)
            ),
            (project_id, *novo_id.keys()),
        )
        for n in sub:
            antigo = n["eap_id"]
            dados = n["dados"]
            uid_no = dados.get("uid") or _gerar_uid()
            conn.execute(
                """
                INSERT INTO eap_node (
                    uid, eap_id, parent_id, nivel, project_id, frente_id, local_id,
                    tipo_frente, nome, unidade, quantidade,
                    descricao, criterio_medicao, responsavel, disciplina,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uid_no,
                    novo_id[antigo],
                    novo_pai_map[novo_id[antigo]],
                    nivel_novo[antigo],
                    project_id,
                    dados.get("frente_id"),
                    dados.get("local_id"),
                    dados.get("tipo_frente"),
                    dados["nome"],
                    dados.get("unidade"),
                    dados.get("quantidade"),
                    dados.get("descricao"),
                    dados.get("criterio_medicao"),
                    dados.get("responsavel"),
                    dados.get("disciplina"),
                    dados.get("created_at") or _agora_iso(),
                    _agora_iso(),
                ),
            )
            conn.execute(
                "INSERT INTO eap_id_history "
                "(uid, project_id, eap_id_de, eap_id_para, motivo) "
                "VALUES (?, ?, ?, ?, ?)",
                (uid_no, project_id, antigo, novo_id[antigo], motivo),
            )
        conn.commit()

    return {
        "movido": True,
        "eap_id": novo_codigo_raiz,
        "novo_parent_id": novo_pai_map.get(novo_codigo_raiz),
        "nivel": novo_nivel,
        "nos_renumerados": len(sub),
    }


def validar_estrutura(
    project_id: str | None = None,
    *,
    strict_single_root: bool | None = None,
) -> dict[str, Any]:
    """Percorre toda a árvore e reporta problemas de integridade.

    Verifica:
      * duplicidade de EAP_ID (EAP_ID repetido em mais de uma linha);
      * nós órfãos (PARENT_ID aponta para um EAP_ID que não existe);
      * NIVEL inconsistente com a posição real na árvore (pai.nivel + 1);
      * quantidade em nó não-folha (dupla contagem de quantitativos);
      * tipo_frente do filho divergente do pai nos níveis >= 2 (coerência).

    Além dos ``problemas`` (integridade estrutural — invalidam a árvore), devolve
    ``avisos`` semânticos que NÃO invalidam: múltiplas raízes por projeto, nome
    em CAIXA ALTA, agregador carregando unidade de medida e tipo_frente
    divergente já no nível 2. Use ``avisos`` para orientar qualidade sem quebrar
    a auditoria estrutural.
    """
    if project_id is None:
        project_id = DEFAULT_PROJECT_ID
    problemas: list[str] = []
    todos = listar_todos(project_id)

    # 1. Duplicidade de EAP_ID (agora via PK composta, mas mantido para robustez).
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
        filhos = listar_filhos(nodo["eap_id"], project_id)
        # 4/5 coerência de tipo_frente e quantidade em não-folha (acumuladas aqui)
        if nodo.get("quantidade") is not None and filhos:
            problemas.append(
                f"Nó '{nodo['eap_id']}' tem quantidade {nodo['quantidade']} "
                f"mas não é folha — dupla contagem no quantitativo."
            )
        for filho in filhos:
            if nivel_esperado >= 2 and filho.get("tipo_frente") and nodo.get("tipo_frente"):
                if filho["tipo_frente"] != nodo["tipo_frente"]:
                    problemas.append(
                        f"Filho '{filho['eap_id']}' (tipo {filho['tipo_frente']}) "
                        f"diverge do pai '{nodo['eap_id']}' ({nodo['tipo_frente']})."
                    )
            _percorre(filho, nivel_esperado + 1)

    for raiz in _raizes(project_id):
        _percorre(raiz, 1)

    # ── Avisos semânticos (não invalidam a árvore; orientam qualidade) ──
    avisos: list[str] = []
    raizes = _raizes(project_id)
    _strict = STRICT_SINGLE_ROOT if strict_single_root is None else strict_single_root
    if len(todos) > 0 and len(raizes) != 1:
        _msg_multi = (
            f"MULTI_ROOT: projeto tem {len(raizes)} raízes "
            f"({', '.join(r['eap_id'] for r in raizes)}); "
            "exige 1 raiz (a obra) por projeto."
        )
        if _strict:
            problemas.append(_msg_multi)
        else:
            avisos.append(_msg_multi)
    _UNIDADES_MEDIDA = {"m²", "m³", "ml", "kg"}

    def _semantica(nodo: dict[str, Any], nivel: int) -> None:
        filhos = listar_filhos(nodo["eap_id"], project_id)
        nome = nodo.get("nome") or ""
        if nome.isupper() and any(ch.isalpha() for ch in nome):
            avisos.append(
                f"Nó '{nodo['eap_id']}' com nome em CAIXA ALTA "
                f"({nome[:45]!r}): prefira Capitalização de Frase."
            )
        if filhos and nodo.get("unidade") in _UNIDADES_MEDIDA:
            avisos.append(
                f"Nó '{nodo['eap_id']}' é agregador (tem {len(filhos)} filho(s)) "
                f"mas carrega unidade de medida '{nodo.get('unidade')}': "
                "deixe a unidade para as folhas."
            )
        if not filhos and not (nodo.get("responsavel") or "").strip():
            avisos.append(
                f"SEM_DONO: folha '{nodo['eap_id']}' ('{nome[:40]}') sem responsável."
            )
        for filho in filhos:
            if (nivel == 1 and filho.get("tipo_frente") and nodo.get("tipo_frente")
                    and nodo.get("tipo_frente") != "projeto"
                    and filho["tipo_frente"] != nodo["tipo_frente"]):
                avisos.append(
                    f"Filho '{filho['eap_id']}' (tipo {filho['tipo_frente']}) diverge "
                    f"do pai '{nodo['eap_id']}' ({nodo['tipo_frente']}) no nível 2."
                )
            _semantica(filho, nivel + 1)

    for raiz in raizes:
        _semantica(raiz, 1)
    avisos.sort()

    return {
        "resumo": {
            "total_nos": len(todos),
            "total_problemas": len(problemas),
            "total_avisos": len(avisos),
            "arvore_valida": len(problemas) == 0,
        },
        "problemas": problemas,
        "avisos": avisos,
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
    return [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]


def contar_templates() -> int:
    """Retorna total de templates cadastrados."""
    with _connect() as conn:
        cursor = conn.execute("SELECT COUNT(*) AS n FROM eap_template_real")
        row = cursor.fetchone()
    return row["n"] if row else 0
