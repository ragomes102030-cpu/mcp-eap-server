"""Bateria F1.1 via MCP: uid nas tools + get por uid/eap antigo + move com motivo."""
from __future__ import annotations

import asyncio, json, os, pathlib, socket, subprocess, sys, time

PASTA = pathlib.Path(__file__).resolve().parent
PORTA = 18088
URL = f"http://127.0.0.1:{PORTA}/mcp"
LOG = PASTA / "_teste_f11.txt"
_linhas, _falhas, _passou = [], 0, 0


def log(m):
    print(m, flush=True)
    _linhas.append(m)
    LOG.write_text("\n".join(_linhas), encoding="utf-8")


def ok(c, m):
    global _falhas, _passou
    if c:
        _passou += 1
    else:
        _falhas += 1
    log(f"  [{'PASS' if c else 'FAIL'}] {m}")


def _espera():
    fim = time.time() + 30
    while time.time() < fim:
        try:
            with socket.create_connection(("127.0.0.1", PORTA), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


async def call(name, args, timeout=20):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as s:
            await asyncio.wait_for(s.initialize(), timeout=timeout)
            res = await asyncio.wait_for(s.call_tool(name, args), timeout=timeout)
    return json.loads(res.content[0].text)


async def main():
    log("=== BAT. F1.1 UID (MCP) ===")
    proc = subprocess.Popen([sys.executable, "_launch_test_server.py"], cwd=str(PASTA),
                            env=dict(os.environ, PORT=str(PORTA)),
                            stdout=open(PASTA / "_f11_run.log", "w", encoding="utf-8"),
                            stderr=subprocess.STDOUT)
    try:
        if not _espera():
            log("FALHA: servidor nao subiu")
            return
        # seed: captura uid do 1.1 e 1.1.1
        a = await call("get_eap_node", {"eap_id": "1.1"})
        uid1 = a.get("uid")
        b = await call("get_eap_node", {"eap_id": "1.1.1"})
        uid2 = b.get("uid")
        ok(uid1 and uid2, f"nodes retornam uid (1.1={uid1[:8]}..)")
        # get por uid
        g = await call("get_eap_node", {"uid": uid1})
        ok(g.get("eap_id") == "1.1" and g.get("uid") == uid1, "get por uid acha o mesmo no")
        # criar no retorna uid
        novo = await call("criar_eap_node", {"nome": "Teste UID", "parent_id": "1.1",
                                             "frente_id": "FR-001",
                                             "tipo_frente": "fundacao",
                                             "unidade": "m³", "quantidade": 5.0})
        uid_novo = novo.get("uid")
        ok(uid_novo, "criar_eap_node retorna uid no payload")
        # move com motivo preserva uid
        mov = await call("move_eap_node", {"eap_id": "1.1", "novo_parent_id": "2",
                                           "motivo": "teste f11"})
        ok(mov.get("eap_id") == "2.2" and mov.get("nos_renumerados", 0) == 4,
           f"move 1.1 -> 2.2 (nos={mov.get('nos_renumerados')})")
        g2 = await call("get_eap_node", {"uid": uid1})
        ok(g2.get("eap_id") == "2.2" and g2.get("uid") == uid1,
           f"uid preservado apos move (agora {g2.get('eap_id')})")
        g3 = await call("get_eap_node", {"uid": uid2})
        ok(g3.get("eap_id") == "2.2.1", "descendente acompanhou e preservou uid")
        # get por eap_id antigo resolve via history
        g4 = await call("get_eap_node", {"eap_id": "1.1"})
        ok(g4.get("uid") == uid1 and g4.get("movido_de") == "1.1"
           and g4.get("movido_para") == "2.2",
           f"get pelo eap_id antigo 1.1 devolve movido_para={g4.get('movido_para')}")
        # ciclo continua bloqueado
        ciclo = await call("move_eap_node", {"eap_id": "2", "novo_parent_id": "2.2"})
        ok("erro" in ciclo and "ciclo" in ciclo.get("erro", "").lower(),
           "ciclo bloqueado (msg contem ciclo)")
        log(f"RESULTADO: {_passou} PASS, {_falhas} FAIL")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log("=== FIM ===")
        if _falhas:
            sys.exit(1)


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(main())
