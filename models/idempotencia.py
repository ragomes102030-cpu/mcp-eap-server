"""Idempotência das tools de escrita: cache de resposta por ``request_id``.

Reenviar o mesmo ``request_id`` devolve a resposta anterior em vez de
executar de novo — evita duplicar nós quando um cliente MCP faz retry após
timeout. Registros são removidos a cada inicialização (TTL de 24h, ver
``limpar_idempotencia_antiga`` chamado no boot do server.py).
"""

from __future__ import annotations

import json
from typing import Any

from .db import _connect


def verificar_idempotencia(request_id: str) -> dict[str, Any] | None:
    """Retorna a resposta cacheada p/ um request_id, ou None se não processado."""
    if not request_id:
        return None
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT response FROM eap_idempotency WHERE request_id = ?",
            (request_id,),
        )
        row = cursor.fetchone()
    if row:
        return json.loads(row["response"])
    return None


def salvar_idempotencia(
    request_id: str, tool_name: str, payload: Any, response: Any
) -> None:
    """Salva a resposta de uma tool para idempotência."""
    if not request_id:
        return
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO eap_idempotency (request_id, tool_name, payload, response)
            VALUES (?, ?, ?, ?)
            """,
            (request_id, tool_name, json.dumps(payload), json.dumps(response)),
        )
        conn.commit()


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
