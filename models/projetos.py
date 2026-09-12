"""CRUD de projetos/obras (``eap_project``).

Depende de ``db`` e de ``nodes`` (``criar_projeto`` já cria a raiz da EAP via
``nodes.inserir_nodo``/``nodes.proximo_eap_id``) — nunca o contrário:
``nodes.py`` não importa daqui, pra evitar ciclo de import.
"""

from __future__ import annotations

from typing import Any

from .db import _connect, _to_dict
from .nodes import inserir_nodo, proximo_eap_id

_PROJETO_CAMPOS = (
    "project_id, nome, tipo_obra, area_m2, metodo_construtivo, regiao, "
    "cliente, ativo, created_at, updated_at"
)


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
    """Cria os metadados de um novo projeto (obra) e a raiz da EAP.

    A raiz é o nó ``[projeto]`` (nível 1, ``nome`` = nome da obra). Erro se o
    projeto já existir.
    """
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

    # F1.2 - projeto = obra: já cria a raiz da EAP (nó 'projeto', nível 1).
    eap_raiz = proximo_eap_id(None, pid)
    inserir_nodo({
        "project_id": pid, "eap_id": eap_raiz, "parent_id": None,
        "nivel": 1, "frente_id": "", "local_id": None,
        "tipo_frente": "projeto", "nome": nome or pid,
        "unidade": None, "quantidade": None,
    })
    resultado = buscar_projeto(pid)
    if resultado is not None:
        resultado["total_nos"] = 1
    return resultado  # type: ignore[return-value]


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


def contar_projetos() -> int:
    """Retorna o total de projetos cadastrados (para metadados de paginação)."""
    with _connect() as conn:
        cursor = conn.execute("SELECT COUNT(*) AS n FROM eap_project")
        row = cursor.fetchone()
    return row["n"] if row else 0


def listar_projetos(
    limit: int | None = None, offset: int = 0
) -> list[dict[str, Any]]:
    """Lista projetos com metadados e a contagem de nós (0 se vazio).

    ``limit``/``offset`` paginam o resultado (ordenado por ``project_id``).
    Sem ``limit``, devolve todos — mantém compatibilidade com chamadas antigas.
    """
    sql = """
        SELECT p.project_id, p.nome, p.tipo_obra, p.area_m2,
               p.metodo_construtivo, p.regiao, p.cliente, p.ativo,
               p.created_at, p.updated_at,
               COUNT(n.project_id) AS total_nos
        FROM eap_project p
        LEFT JOIN eap_node n ON n.project_id = p.project_id
        GROUP BY p.project_id
        ORDER BY p.project_id
    """
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
    with _connect() as conn:
        cursor = conn.execute(sql, tuple(params))
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
