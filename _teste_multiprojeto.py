"""Bateria Fase A - MULTI-OBRA (projeto = obra de primeira classe)."""
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
PORTA = 18086
URL = f"http://127.0.0.1:{PORTA}/mcp"
LOG = PASTA / "_teste_multiprojeto.txt"
OUT = PASTA / "_teste_multiprojeto_run.log"
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
    log("=== BAT. FASE A - MULTI-OBRA ===")
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
                ok(len(nomes) == 18, f"tools/list expoe 18 tools (tem {len(nomes)})")
                ok("buscar_eap_node" in nomes, "buscar_eap_node presente (Fase 2 §3)")
                ok("criar_projeto" in nomes and "atualizar_projeto" in nomes,
                   "tools de projeto presentes")

                prjs = await call("listar_projetos", {})
                ok(prjs["total_projetos"] == 1 and prjs["total_nos"] == 9,
                   f"listar_projetos inicial: {prjs['total_projetos']} proj / {prjs['total_nos']} nos")
                default = prjs["projetos"][0]
                ok(default["project_id"] == "default" and default["nome"] == "Piemarta (exemplo)",
                   f"default metadados: nome={default.get('nome')!r}")
                ok(default["total_nos"] == 9 and default["tipo_obra"] == "edificio_residencial",
                   f"default: nos={default['total_nos']}, tipo={default.get('tipo_obra')!r}")

                val = await call("validar_estrutura", {})
                ok(val["resumo"]["total_nos"] == 9 and val["resumo"]["arvore_valida"] is True,
                   "validar default: 9 nos validos (retroativo intacto)")
                tree = await call("get_eap_tree", {})
                ok([x["eap_id"] for x in tree["raizes"]] == ["1", "2"],
                   "get_eap_tree default mantem raizes 1 e 2")

                novo = await call("criar_projeto", {
                    "project_id": "OBRA-2", "nome": "Residencial Teste",
                    "tipo_obra": "casa", "area_m2": 120.0,
                    "metodo_construtivo": "alvenaria_estrutural",
                    "regiao": "sudeste", "cliente": "Cliente Exemplo LTDA",
                })
                ok(novo.get("project_id") == "OBRA-2" and novo.get("total_nos") == 1,
                   f"criar_projeto OBRA-2 cria a raiz (nos={novo.get('total_nos')})")
                dup = await call("criar_projeto", {"project_id": "OBRA-2", "nome": "duplicado"})
                ok("erro" in dup and "já existe" in dup.get("erro", ""),
                   f"criar_projeto duplicado rejeitado: {dup.get('erro','')[:50]}")
                noex = await call("atualizar_projeto", {"project_id": "nao-existe", "nome": "x"})
                ok("erro" in noex, "atualizar_projeto inexistente -> erro")

                raiz_auto = await call("get_eap_node", {"eap_id": "1", "project_id": "OBRA-2"})
                ok(raiz_auto.get("tipo_frente") == "projeto"
                   and raiz_auto.get("nome") == "Residencial Teste",
                   f"criar_projeto cria raiz [projeto]: {raiz_auto.get('nome')!r}")
                fase = await call("criar_eap_node", {
                    "project_id": "OBRA-2", "nome": "FUNDACOES", "parent_id": "1",
                    "frente_id": "FR-A", "local_id": "CASA-1", "tipo_frente": "fundacao",
                })
                ok(fase.get("eap_id") == "1.1" and fase.get("nivel") == 2,
                   f"OBRA-2 fase sob raiz automatica: {fase.get('eap_id')}")
                leaf = await call("criar_eap_node", {
                    "project_id": "OBRA-2", "nome": "SAPATA TIPO 1", "parent_id": "1.1",
                    "frente_id": "FR-A", "local_id": "CASA-1",
                    "tipo_frente": "fundacao", "unidade": "m³", "quantidade": 24.0,
                })
                ok(leaf.get("eap_id") == "1.1.1", "OBRA-2 filho 1.1.1")
                viga = await call("criar_eap_node", {
                    "project_id": "OBRA-2", "nome": "VIGA BALDRAME", "parent_id": "1.1",
                    "frente_id": "FR-A", "local_id": "CASA-1",
                    "tipo_frente": "fundacao", "unidade": "m³", "quantidade": 8.0,
                })
                ok(viga.get("eap_id") == "1.1.2", "OBRA-2 filho 1.1.2")

                # ---- 4) ISOLAMENTO entre projetos ----
                no_default = await call("get_eap_node", {"eap_id": "1"})
                no_obra2 = await call("get_eap_node", {"eap_id": "1", "project_id": "OBRA-2"})
                ok(no_default.get("nome") == "FUNDAÇÕES"
                   and no_obra2.get("nome") == "Residencial Teste",
                   f"mesmo eap_id '1': default={no_default.get('nome')!r} vs OBRA-2={no_obra2.get('nome')!r}")
                filho_default = await call("get_eap_node", {"eap_id": "1.1.1"})
                filho_obra2 = await call("get_eap_node", {"eap_id": "1.1.1", "project_id": "OBRA-2"})
                ok(filho_default.get("nome") == "ESCAVAÇÃO SAPATAS"
                   and filho_obra2.get("nome") == "SAPATA TIPO 1",
                   "subnos independentes entre projetos")

                val2 = await call("validar_estrutura", {"project_id": "OBRA-2"})
                ok(val2["resumo"]["total_nos"] == 4 and val2["resumo"]["arvore_valida"] is True,
                   "validar OBRA-2: 4 nos validos (raiz + fase + 2 folhas)")
                val_def = await call("validar_estrutura", {})
                ok(val_def["resumo"]["total_nos"] == 9,
                   "validar default nao contaminado pela OBRA-2")

                tree2 = await call("get_eap_tree", {"project_id": "OBRA-2"})
                ok([x["eap_id"] for x in tree2["raizes"]] == ["1"],
                   "get_eap_tree OBRA-2: somente raiz 1")
                por_tipo = await call("listar_por_tipo_frente",
                                      {"tipo_frente": "fundacao", "project_id": "OBRA-2"})
                ok(por_tipo["total"] == 3, f"listar_por_tipo_frente OBRA-2 fundacao: {por_tipo['total']}")
                por_tipo_def = await call("listar_por_tipo_frente", {"tipo_frente": "fundacao"})
                ok(por_tipo_def["total"] == 4, f"listar_por_tipo_frente default fundacao: {por_tipo_def['total']}")

                # ---- 5) UPDATE/MOVE/DELETE escopados ao projeto ----
                upd = await call("atualizar_eap_node", {
                    "eap_id": "1.1.1", "project_id": "OBRA-2", "nome": "SAPATA TIPO 1 REV A",
                })
                ok(upd.get("nome") == "SAPATA TIPO 1 REV A", "atualizar no na OBRA-2 (escopado)")
                mov = await call("move_eap_node", {
                    "eap_id": "1.1.2", "novo_parent_id": None, "project_id": "OBRA-2",
                    "motivo": "teste isolamento move",
                })
                ok(mov.get("movido") is True and mov.get("eap_id") == "2"
                   and mov.get("nivel") == 1,
                   f"mover OBRA-2 1.1.2 p/ raiz vira {mov.get('eap_id')}")
                delx = await call("deletar_eap_node", {
                    "eap_id": "2", "cascade": True, "project_id": "OBRA-2",
                })
                ok(delx.get("deletado") is True, "deletar subarvore na OBRA-2")
                val3 = await call("validar_estrutura", {"project_id": "OBRA-2"})
                ok(val3["resumo"]["total_nos"] == 3, f"OBRA-2 apos move/delete: {val3['resumo']['total_nos']} nos")

                # ---- 6) METADADOS + LISTA + LIMPEZA ----
                updp = await call("atualizar_projeto", {
                    "project_id": "OBRA-2", "nome": "Residencial Teste REV B", "area_m2": 200.0,
                })
                ok(updp.get("nome") == "Residencial Teste REV B" and updp.get("area_m2") == 200.0,
                   f"atualizar_projeto OK: {updp.get('nome')} / {updp.get('area_m2')} m2")
                prjs2 = await call("listar_projetos", {})
                mapa = {p["project_id"]: p for p in prjs2["projetos"]}
                ok(prjs2["total_projetos"] == 2 and mapa["OBRA-2"]["total_nos"] == 3,
                   f"listar_projetos: 2 projetos (OBRA-2={mapa.get('OBRA-2',{}).get('total_nos')} nos)")
                ok(mapa["OBRA-2"]["nome"] == "Residencial Teste REV B",
                   "listar_projetos reflete metadados atualizados")

                raiz_imp = await call("criar_eap_node", {
                    "project_id": "obra-sem-metadata", "nome": "RAIZ",
                    "frente_id": "FR-X", "tipo_frente": "estrutura",
                })
                ok(raiz_imp.get("eap_id") == "1", "criar no em projeto sem metadados: ok (auto-registro)")
                prjs3 = await call("listar_projetos", {})
                mapa3 = {p["project_id"]: p for p in prjs3["projetos"]}
                ok("obra-sem-metadata" in mapa3 and mapa3["obra-sem-metadata"]["total_nos"] == 1,
                   "projeto implicito aparece no listar_projetos")

                dep = await call("deletar_projeto", {"project_id": "OBRA-2"})
                ok(dep.get("deletado") is True and dep.get("total_nos") == 3,
                   f"deletar_projeto OBRA-2 remove nos+metadados ({dep.get('total_nos')} removidos)")
                dep2 = await call("deletar_projeto", {"project_id": "obra-sem-metadata"})
                ok(dep2.get("deletado") is True and dep2.get("total_nos") == 1,
                   "deletar_projeto implicito (sem-metadata) OK")
                prjs4 = await call("listar_projetos", {})
                ok(prjs4["total_projetos"] == 1 and prjs4["total_nos"] == 9,
                   f"fim: volta a 1 projeto / {prjs4['total_nos']} nos")

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

