"""Registro de escopo e auditoria da Regra dos 100% da EAP.

O escopo é mantido separado da árvore para que a cobertura seja auditável:
um item obrigatório do escopo deve possuir exatamente um vínculo principal
com um nó da EAP. Nós de gestão/suporte podem existir sem representar escopo
físico e são classificados pelo campo categoria.
"""
from __future__ import annotations

from typing import Any
import uuid

from .db import DEFAULT_PROJECT_ID, _connect, _garantir_projeto


CATEGORIAS_VALIDAS = {
    "deliverable",
    "system",
    "requirement",
    "management",
    "support",
    "enabling",
}


def _pid(project_id: str | None) -> str:
    return (project_id or "").strip() or DEFAULT_PROJECT_ID


def criar_item_escopo(
    descricao: str,
    project_id: str | None = None,
    *,
    code: str | None = None,
    tipo: str = "deliverable",
    fonte: str | None = None,
    quantidade: float | None = None,
    unidade: str | None = None,
    obrigatorio: bool = True,
    scope_id: str | None = None,
) -> dict[str, Any]:
    pid = _pid(project_id)
    descricao = descricao.strip()
    if not descricao:
        raise ValueError("descricao do escopo é obrigatória.")
    if tipo not in CATEGORIAS_VALIDAS:
        raise ValueError(f"tipo de escopo inválido: {tipo}.")
    if quantidade is not None and quantidade < 0:
        raise ValueError("quantidade do escopo não pode ser negativa.")
    _garantir_projeto(pid)
    sid = (scope_id or "").strip() or uuid.uuid4().hex
    with _connect() as conn:
        conn.execute(
            """INSERT INTO eap_scope_item
               (scope_id, project_id, code, descricao, tipo, fonte,
                quantidade, unidade, obrigatorio, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ativo')""",
            (sid, pid, code, descricao, tipo, fonte, quantidade, unidade,
             1 if obrigatorio else 0),
        )
        conn.commit()
    return buscar_item_escopo(sid, pid)  # type: ignore[return-value]


def buscar_item_escopo(scope_id: str, project_id: str | None = None) -> dict[str, Any] | None:
    pid = _pid(project_id)
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM eap_scope_item WHERE scope_id = ? AND project_id = ?",
            (scope_id, pid),
        ).fetchone()
    return dict(row) if row else None


def listar_escopo(project_id: str | None = None, *, apenas_ativos: bool = True) -> list[dict[str, Any]]:
    pid = _pid(project_id)
    sql = "SELECT * FROM eap_scope_item WHERE project_id = ?"
    params: list[Any] = [pid]
    if apenas_ativos:
        sql += " AND status = 'ativo'"
    sql += " ORDER BY code, created_at, scope_id"
    with _connect() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def vincular_escopo_eap(
    scope_id: str,
    eap_id: str,
    project_id: str | None = None,
    *,
    papel: str = "principal",
) -> dict[str, Any]:
    pid = _pid(project_id)
    if papel not in {"principal", "secundario"}:
        raise ValueError("papel deve ser 'principal' ou 'secundario'.")
    with _connect() as conn:
        scope = conn.execute(
            "SELECT * FROM eap_scope_item WHERE scope_id = ? AND project_id = ?",
            (scope_id, pid),
        ).fetchone()
        node = conn.execute(
            "SELECT uid, eap_id, nome FROM eap_node WHERE project_id = ? AND eap_id = ?",
            (pid, eap_id),
        ).fetchone()
        if not scope:
            raise ValueError("item de escopo não encontrado no projeto.")
        if not node:
            raise ValueError("nó EAP não encontrado no projeto.")
        if papel == "principal":
            existente = conn.execute(
                """SELECT scope_id FROM eap_scope_coverage
                   WHERE project_id = ? AND scope_id = ? AND papel = 'principal'""",
                (pid, scope_id),
            ).fetchone()
            if existente and existente["scope_id"] != scope_id:
                raise ValueError("item de escopo já possui vínculo principal.")
        conn.execute(
            """INSERT OR REPLACE INTO eap_scope_coverage
               (project_id, scope_id, eap_uid, eap_id, papel)
               VALUES (?, ?, ?, ?, ?)""",
            (pid, scope_id, node["uid"], node["eap_id"], papel),
        )
        conn.commit()
    return {
        "project_id": pid, "scope_id": scope_id, "eap_uid": node["uid"],
        "eap_id": node["eap_id"], "eap_nome": node["nome"], "papel": papel,
    }


def desvincular_escopo_eap(
    scope_id: str,
    eap_id: str | None = None,
    project_id: str | None = None,
) -> int:
    pid = _pid(project_id)
    with _connect() as conn:
        if eap_id:
            cur = conn.execute(
                "DELETE FROM eap_scope_coverage WHERE project_id = ? AND scope_id = ? AND eap_id = ?",
                (pid, scope_id, eap_id),
            )
        else:
            cur = conn.execute(
                "DELETE FROM eap_scope_coverage WHERE project_id = ? AND scope_id = ?",
                (pid, scope_id),
            )
        conn.commit()
        return cur.rowcount


def listar_coberturas(project_id: str | None = None) -> list[dict[str, Any]]:
    pid = _pid(project_id)
    with _connect() as conn:
        rows = conn.execute(
            """SELECT c.*, s.code AS scope_code, s.descricao AS scope_descricao,
                      s.obrigatorio, n.nome AS eap_nome
               FROM eap_scope_coverage c
               JOIN eap_scope_item s
                 ON s.project_id = c.project_id AND s.scope_id = c.scope_id
               LEFT JOIN eap_node n
                 ON n.project_id = c.project_id AND n.uid = c.eap_uid
               WHERE c.project_id = ?
               ORDER BY s.code, c.scope_id""",
            (pid,),
        ).fetchall()
    return [dict(r) for r in rows]


def validar_100_porcento(project_id: str | None = None) -> dict[str, Any]:
    pid = _pid(project_id)
    escopo = listar_escopo(pid)
    coberturas = listar_coberturas(pid)
    obrigatorios = [s for s in escopo if s["obrigatorio"]]
    by_scope: dict[str, list[dict[str, Any]]] = {}
    for c in coberturas:
        by_scope.setdefault(c["scope_id"], []).append(c)

    sem_eap: list[dict[str, Any]] = []
    sobreposicoes: list[dict[str, Any]] = []
    for s in obrigatorios:
        links = by_scope.get(s["scope_id"], [])
        principais = [x for x in links if x["papel"] == "principal"]
        if len(principais) == 0:
            sem_eap.append({
                "scope_id": s["scope_id"], "code": s["code"],
                "descricao": s["descricao"],
            })
        elif len(principais) > 1:
            sobreposicoes.append({
                "scope_id": s["scope_id"], "links_principais": principais,
            })

    eap_sem_escopo: list[dict[str, Any]] = []
    with _connect() as conn:
        rows = conn.execute(
            """SELECT n.uid, n.eap_id, n.nome, n.tipo_frente
               FROM eap_node n
               WHERE n.project_id = ?
                 AND NOT EXISTS (
                   SELECT 1 FROM eap_scope_coverage c
                   WHERE c.project_id = n.project_id AND c.eap_uid = n.uid
                 )
                 AND COALESCE(n.tipo_frente, '') NOT IN ('projeto')""",
            (pid,),
        ).fetchall()
    # Nós agregadores/gestão podem existir legitimamente fora do escopo físico.
    # Eles são alertas, não falhas, até a classificação formal do nó ser criada.
    eap_sem_escopo = [dict(r) for r in rows]

    total = len(obrigatorios)
    cobertos = total - len(sem_eap)
    percentual = round((cobertos / total) * 100, 2) if total else 0.0
    if not escopo:
        status = "SEM_BASE_DE_ESCOPO"
    elif sem_eap or sobreposicoes:
        status = "REPROVADA"
    else:
        status = "APROVAVEL"

    return {
        "project_id": pid,
        "percentual_cobertura": percentual,
        "escopo_total": total,
        "escopo_coberto": cobertos,
        "escopo_sem_eap": sem_eap,
        "eap_sem_escopo": eap_sem_escopo,
        "sobreposicoes": sobreposicoes,
        "status": status,
        "regra": "100% do escopo obrigatório deve ter exatamente um vínculo principal com a EAP.",
    }
