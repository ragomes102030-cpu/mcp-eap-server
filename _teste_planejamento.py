"""Bateria funcional do MCP EAP - visao 'engenheiro de planejamento'.

Sobe um servidor isolado (porta 18085, sqlite temporario, codigo atual) e
exercita as 13 tools em um roteiro realista de planejamento de obra.
"""
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
PORTA = 18085
URL = f"http://127.0.0.1:{PORTA}/mcp"
LOG = PASTA / "_teste_planejamento.txt"
OUT = PASTA / "_teste_planejamento_run.log"
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
    log("=== BAT. FUNCIONAL MCP EAP (eng. planejamento) ===")

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
                tools = await s.list_tools()
                nomes = sorted(t.name for t in tools.tools)
                ok(len(nomes) == 15, f"tools/list expoe 15 tools (tem {len(nomes)})")
                ok("move_eap_node" in nomes and "validar_estrutura" in nomes,
                   "tools criticas presentes (move_eap_node, validar_estrutura)")

                # ---- 1) CONSULTAS INICIAIS (seed Piemarta) ----
                val = await call("validar_estrutura", {})
                ok(val["resumo"]["total_nos"] == 9, f"seed: 9 nos (tem {val['resumo']['total_nos']})")
                ok(val["resumo"]["arvore_valida"] is True, "validar_estrutura inicial: arvore valida")
                tree = await call("get_eap_tree", {})
                raizes = [x["eap_id"] for x in tree["raizes"]]
                ok(raizes == ["1", "2"], f"raizes do seed: {raizes}")
                no = await call("get_eap_node", {"eap_id": "1.1.1"})
                ok(no["nome"] == "ESCAVAÇÃO SAPATAS", f"get_eap_node 1.1.1 -> {no['nome']}")
                ltf = await call("listar_por_tipo_frente", {"tipo_frente": "fundacao"})
                ok(ltf["total"] >= 4, f"listar_por_tipo_frente(fundacao): {ltf['total']}")
                tpl = await call("listar_templates", {"projeto_tipo": "casa"})
                ok(tpl["total"] > 0, f"listar_templates(casa): {tpl['total']} templates")
                prj = await call("listar_projetos", {})
                ok(prj["total_projetos"] >= 1 and prj["total_nos"] == 9,
                   f"listar_projetos: {prj['total_projetos']} proj, {prj['total_nos']} nos")

                # ---- 2) PLANEJAMENTO: detalhar fundacao (folha sob SAPATAS) ----
                criado = await call("criar_eap_node", {
                    "nome": "ARMAÇÃO SAPATAS", "parent_id": "1.1",
                    "frente_id": "FR-001", "local_id": "BLOCO-A",
                    "tipo_frente": "fundacao", "unidade": "kg", "quantidade": 950.0,
                    "request_id": "pl-1",
                })
                ok(criado.get("eap_id") == "1.1.3", f"criar sob 1.1 -> EAP_ID {criado.get('eap_id')}")
                ok(criado.get("nivel") == 3 and criado.get("parent_id") == "1.1",
                   f"nivel/pai corretos: nivel={criado.get('nivel')} pai={criado.get('parent_id')}")


                # idempotencia
                criado2 = await call("criar_eap_node", {
                    "nome": "ARMAÇÃO SAPATAS", "parent_id": "1.1",
                    "frente_id": "FR-001", "local_id": "BLOCO-A",
                    "tipo_frente": "fundacao", "unidade": "kg", "quantidade": 950.0,
                    "request_id": "pl-1",
                })
                ok(criado2 == criado, "idempotencia: mesmo request_id retorna resposta identica")
                val2 = await call("validar_estrutura", {})
                ok(val2["resumo"]["total_nos"] == 10, "idempotencia: sem duplicar (10 nos)")

                # negativos: tipo_frente fora do vocabulario / quantidade em
                # no COM FILHOS (rejeitada no update; criar folha c/ qtd e' valido)
                inv = await call("criar_eap_node", {
                    "nome": "INVÁLIDO", "parent_id": None, "tipo_frente": "terraplanagem",
                })
                ok("erro" in inv, f"tipo_frente invalido rejeitado: {inv.get('erro', '')[:70]}")
                invq = await call("atualizar_eap_node", {
                    "eap_id": "1.1", "quantidade": 5.0, "unidade": "m³",
                    "request_id": "pl-q",
                })
                ok("erro" in invq and "folha" in invq.get("erro", "").lower(),
                   f"quantidade em no com filhos rejeitada no update: {invq.get('erro','')[:70]}")

                # ---- 3) EDICAO (atualizar_eap_node) ----
                upd = await call("atualizar_eap_node", {
                    "eap_id": "1.1.3", "nome": "ARMACAO SAPATAS CA-50",
                    "quantidade": 980.0, "request_id": "pl-3",
                })
                ok(upd.get("nome") == "ARMACAO SAPATAS CA-50" and upd.get("quantidade") == 980.0,
                   f"atualizar 1.1.3 -> {upd.get('nome')} qtd {upd.get('quantidade')}")

                # novo item de estrutura (formas de pilares)
                criado2 = await call("criar_eap_node", {
                    "nome": "FORMA PILARES", "parent_id": "2.1",
                    "frente_id": "FR-002", "tipo_frente": "estrutura",
                    "unidade": "m²", "quantidade": 300.0, "request_id": "pl-4",
                })
                ok(criado2.get("eap_id") == "2.1.2", f"criar sob 2.1 -> {criado2.get('eap_id')}")

                # ---- 4) MOVE (reorganizar estrutura: VIGAS p/ sob ESTRUTURA) ----
                mov = await call("move_eap_node", {
                    "eap_id": "1.2", "novo_parent_id": "2", "request_id": "pl-5",
                })
                ok(mov.get("movido") is True and mov.get("eap_id") == "2.2",
                   f"mover 1.2 -> sob 2 vira {mov.get('eap_id')} (nos={mov.get('nos_renumerados')})")
                ok(mov.get("nivel") == 2, f"nivel recalculado: {mov.get('nivel')}")
                # filho da subarvore acompanhou: 1.2.1 -> 2.2.1
                gotfilho = await call("get_eap_node", {"eap_id": "2.2.1"})
                ok(gotfilho.get("parent_id") == "2.2" and gotfilho.get("nivel") == 3,
                   f"descendente renumerado: 2.2.1 (pai={gotfilho.get('parent_id')})")
                # ciclo bloqueado
                ciclo = await call("move_eap_node", {"eap_id": "2", "novo_parent_id": "2.2"})
                ok("erro" in ciclo and "ciclo" in ciclo.get("erro", "").lower(),
                   f"ciclo bloqueado: {ciclo.get('erro','')[:70]}")

                # ---- 5) DELECAO ----
                dell = await call("deletar_eap_node", {"eap_id": "2.1.2", "cascade": False})
                ok(dell.get("deletado") is True, "deletar folha 2.1.2 ok")
                blq = await call("deletar_eap_node", {"eap_id": "2.2", "cascade": False})
                ok("erro" in blq, "deletar no com filho sem cascade rejeitado")
                cas = await call("deletar_eap_node", {"eap_id": "2.2", "cascade": True,
                                                      "request_id": "pl-6"})
                ok(cas.get("deletado") is True, "deletar 2.2 com cascade (remove subarvore)")
                dep = await call("deletar_projeto", {"project_id": "naoexiste"})
                ok(dep.get("deletado") is True and dep.get("total_nos") == 0,
                   "deletar_projeto inexistente nao destrutivo (total_nos=0)")

                # ---- 6) ESTADO FINAL ----
                valf = await call("validar_estrutura", {})
                ok(valf["resumo"]["total_nos"] == 8 and valf["resumo"]["arvore_valida"] is True,
                   f"final: {valf['resumo']['total_nos']} nos validos, problemas={len(valf['problemas'])}")
                treef = await call("get_eap_tree", {})
                log("ARVORE FINAL: " + json.dumps(treef, ensure_ascii=False)[:400])
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

