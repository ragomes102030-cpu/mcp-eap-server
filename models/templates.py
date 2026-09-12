"""CRUD de templates reais de EAP (``eap_template_real``) — referência
histórica de orçamento por tipo de obra."""

from __future__ import annotations

from typing import Any

from .db import _connect
from .validacao import normalizar_unidade


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


def _where_filtros(
    projeto_tipo: str | None,
    area_m2: float | None,
    metodo_construtivo: str | None,
) -> tuple[list[str], list[Any]]:
    """Monta a cláusula WHERE compartilhada por listar/contar templates."""
    where: list[str] = []
    params: list[Any] = []
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
    return where, params


def listar_templates(
    projeto_tipo: str | None = None,
    area_m2: float | None = None,
    metodo_construtivo: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Lista templates com filtros opcionais e paginação (``limit``/``offset``).

    Sem ``limit``, devolve todos — mantém compatibilidade com chamadas antigas.
    """
    where, params = _where_filtros(projeto_tipo, area_m2, metodo_construtivo)

    sql = "SELECT * FROM eap_template_real"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY projeto_tipo, eap_node"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])

    with _connect() as conn:
        cursor = conn.execute(sql, tuple(params))
    return [dict(r) if not isinstance(r, dict) else r for r in cursor.fetchall()]


def contar_templates_filtrados(
    projeto_tipo: str | None = None,
    area_m2: float | None = None,
    metodo_construtivo: str | None = None,
) -> int:
    """Conta templates que casam com os mesmos filtros de ``listar_templates``."""
    where, params = _where_filtros(projeto_tipo, area_m2, metodo_construtivo)
    sql = "SELECT COUNT(*) AS n FROM eap_template_real"
    if where:
        sql += " WHERE " + " AND ".join(where)
    with _connect() as conn:
        cursor = conn.execute(sql, tuple(params))
        row = cursor.fetchone()
    return row["n"] if row else 0


def contar_templates() -> int:
    """Retorna total de templates cadastrados."""
    with _connect() as conn:
        cursor = conn.execute("SELECT COUNT(*) AS n FROM eap_template_real")
        row = cursor.fetchone()
    return row["n"] if row else 0
