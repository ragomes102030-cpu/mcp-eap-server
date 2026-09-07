"""Bateria Fase B - VALIDACAO SEMANTICA (avisos sem invalidar a arvore)."""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import socket
import subprocess
import sys
import time

PASTA = pathlib.Path(__file__).resolve().parent
PORTA = 18087
URL = f"http://127.0.0.1:{PORTA}/mcp"
LOG = PASTA / "_teste_semantica.txt"
OUT = PASTA / "_teste_semantica_run.log"
_linhas: list[str] = []
_falhas = 0
_passou = 0


def log(m: str) -> None:
    print(m, flush=True)
    _linhas.append(m)
    LOG.write_text("\n".join(_linhas), encoding="utf-8")


def ok(cond: bool, msg: str) -> None:
    global _falhas, _passou
    if cond:
        _passou += 1
        log(f"  [PASS] {msg}")
    else:
        _falhas += 1
        log(f"  [FAIL] {msg}")


def _espera_porta(tempo_max: float = 30.0) -> bool:
    fim = time.time() + tempo_max
    while time.time() < fim:
        try:
            with socket.create_connection(("127.0.0.1", PORTA), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


async def call(name: str, args: dict, timeout: float = 20.0) -> dict:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as s:
            await asyncio.wait_for(s.initialize(), timeout=timeout)
            res = await asyncio.wait_for(s.call_tool(name, args), timeout=timeout)
    return json.loads(res.content[0].text)


async def main() -> None:
    log("=== BAT. FASE B - VALIDACAO SEMANTICA ===")
    env = dict(os.environ, PORT=str(PORTA))
    proc = subprocess.Popen(
        [sys.executable, "_launch_test_server.py"],
        cwd=str(PASTA), env=env,
        stdout=open(OUT, "w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    try:
        if not _espera_porta():
            log("FALHA: servidor de teste nao subiu")
            return
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(URL) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()

                # seed Piemarta (default): integridade OK, mas avisos semanticos
                val = await call("validar_estrutura", {})
                res = val["resumo"]
                ok(res["total_nos"] == 9, "seed: 9 nos")
                ok(res["total_problemas"] == 0 and res["arvore_valida"] is True,
                   "seed: 0 problemas estruturais (arvore_valida True)")
                ok("total_avisos" in res and res["total_avisos"] > 0,
                   f"seed: total_avisos={res.get('total_avisos')} (>0)")
                ok("avisos" in val and isinstance(val["avisos"], list),
                   "resposta expoe lista 'avisos'")
                txts = "\n".join(val["avisos"])
                ok("raízes" in txts or "raizes" in txts,
                   "aviso de multiplas raizes presente (seed tem raizes 1 e 2)")
                ok("CAIXA ALTA" in txts, "aviso de nome em CAIXA ALTA presente")
                ok("diverge do pai '1'" in txts,
                   "aviso tipo_frente divergente no nivel 2 presente (1.2 sob 1)")
                log("  AVISOS SEED: " + json.dumps(val["avisos"], ensure_ascii=False)[:600])

                # projeto "limpo" (raiz automatica [projeto], nomes capitalizados,
                # tipos coerentes, folha com dono)
                await call("criar_projeto", {
                    "project_id": "OBRA-CLEAN", "nome": "Obra Limpa",
                    "tipo_obra": "apartamento", "area_m2": 80.0,
                })
                await call("criar_eap_node", {
                    "project_id": "OBRA-CLEAN", "nome": "Estrutura", "parent_id": "1",
                    "frente_id": "FR-A", "local_id": "AP-1", "tipo_frente": "estrutura",
                })
                await call("criar_eap_node", {
                    "project_id": "OBRA-CLEAN", "nome": "Concreto pilares",
                    "parent_id": "1.1", "frente_id": "FR-A", "local_id": "AP-1",
                    "tipo_frente": "estrutura", "unidade": "m³", "quantidade": 12.0,
                })
                await call("definir_criterio", {"eap_id": "1.1.1", "project_id": "OBRA-CLEAN",
                                                "responsavel": "Equipe de estrutura"})
                valc = await call("validar_estrutura", {"project_id": "OBRA-CLEAN"})
                rc = valc["resumo"]
                ok(rc["total_nos"] == 3 and rc["total_problemas"] == 0
                   and rc["arvore_valida"] is True,
                   "OBRA-CLEAN: 3 nos, 0 problemas")
                ok(rc["total_avisos"] == 0, f"OBRA-CLEAN: 0 avisos (tem {rc['total_avisos']})")
                log("  AVISOS CLEAN: " + json.dumps(valc["avisos"], ensure_ascii=False))

                log(f"RESULTADO: {_passou} PASS, {_falhas} FAIL")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log("=== FIM DA BATERIA ===")
        if _falhas:
            sys.exit(1)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(main())
