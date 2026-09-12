"""Logging estruturado (JSON, uma linha por evento) para chamadas de tool MCP.

Escreve em stderr (padrão de containers/Render: stdout/stderr viram log do
serviço). Cada chamada de tool gera uma linha ``inicio`` e uma ``fim`` com
duração, status (ok/erro) e, em caso de erro, a mensagem — sem payload
completo, para não vazar dados de negócio nem inflar o log.

Uso:
    with log_tool_call("criar_eap_node", project_id="obra-1"):
        ...

``log_tool_call`` não decide o que é erro para você: se o bloco levantar uma
exceção, ela é logada e re-levantada (o comportamento de _seguro/_idempotente
em server.py continua responsável por transformar exceções em ErroOutput).
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emitir(evento: dict[str, Any]) -> None:
    print(json.dumps(evento, ensure_ascii=False), file=sys.stderr, flush=True)


@contextmanager
def log_tool_call(tool_name: str, **contexto: Any) -> Iterator[None]:
    """Loga início/fim de uma chamada de tool MCP em formato JSON estruturado.

    ``contexto`` são campos extras não sensíveis (ex.: project_id, eap_id) —
    nunca passe aqui payloads completos de entrada do usuário.
    """
    inicio = time.monotonic()
    _emitir({"evento": "tool_inicio", "tool": tool_name, "ts": _timestamp(), **contexto})
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - relogamos e propagamos
        duracao_ms = round((time.monotonic() - inicio) * 1000, 2)
        _emitir({
            "evento": "tool_erro",
            "tool": tool_name,
            "ts": _timestamp(),
            "duracao_ms": duracao_ms,
            "erro_tipo": type(exc).__name__,
            "erro_msg": str(exc),
            **contexto,
        })
        raise
    else:
        duracao_ms = round((time.monotonic() - inicio) * 1000, 2)
        _emitir({
            "evento": "tool_fim",
            "tool": tool_name,
            "ts": _timestamp(),
            "duracao_ms": duracao_ms,
            **contexto,
        })
