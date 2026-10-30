#!/usr/bin/env python3
"""Safe, dependency-free remote MCP interoperability smoke test.

Tests deployed public endpoints with legacy Streamable HTTP and probes
2026-07-28 (modern). Never sends writes or credentials.
Usage: MCP_TARGET=eap|cronograma|gantt_lob python scripts/check_public_mcp.py
"""
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

HOSTS = {
    "eap": "https://arquimedes-mcp-eap.vercel.app",
    "cronograma": "https://arquimedes-mcp-cronograma.vercel.app",
    "gantt_lob": "https://arquimedes-mcp-gantt-lob.vercel.app",
}
EXPECTED = {
    "eap": {"avaliar_evidencia_eap", "validar_estrutura_eap"},
    "cronograma": {"calcular_duracao_com_evidencia", "calcular_cpm_com_evidencia"},
    "gantt_lob": {
        "calcular_linha_balanco", "balancear_ritmos_lob",
        "dimensionar_equipes_lob", "listar_temas",
    },
}
DANGEROUS = {
    "deletar_projeto", "deletar_atividade", "criar_projeto", "criar_atividade",
    "salvar_baseline", "listar_exports", "gerar_gantt", "criar_eap_node",
}
TARGET = os.getenv("MCP_TARGET", "").strip()
ROOT = os.getenv("MCP_BASE_URL") or HOSTS.get(TARGET)
CHECKS = []
MODERN = False


def request(path, payload=None, headers=None, method=None):
    if not ROOT:
        raise ValueError("Set MCP_TARGET=eap|cronograma|gantt_lob or MCP_BASE_URL")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    h = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    h.update(headers or {})
    req = urllib.request.Request(ROOT + path, body, headers=h,
                                 method=method or ("POST" if body else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            status, raw = resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read().decode("utf-8", "replace")
    if not raw:
        return status, {}
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        # Legacy MCP allows an SSE stream as the response to POST.
        for line in reversed(raw.splitlines()):
            if line.startswith("data:"):
                return status, json.loads(line[5:].strip())
        raise AssertionError(f"Non-JSON response: HTTP {status}, {raw[:150]!r}")


def record(name, fn):
    try:
        detail = fn()
        CHECKS.append({"check": name, "status": "pass", "detail": detail})
        print(f"PASS {name}: {detail}", flush=True)
    except Exception as exc:
        CHECKS.append({"check": name, "status": "fail", "detail": str(exc)})
        print(f"FAIL {name}: {exc}", flush=True)


def rpc(method, params=None, *, extra_headers=None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    status, response = request("/public-mcp", payload, headers=extra_headers)
    if status != 200 or "error" in response or "result" not in response:
        raise AssertionError(f"{method}: HTTP {status} {str(response)[:400]}")
    return response["result"]


def unwrap(result):
    if result.get("isError"):
        raise AssertionError(f"MCP tool error: {str(result)[:400]}")
    structured = result.get("structuredContent")
    if structured is not None:
        return structured.get("result", structured) if isinstance(structured, dict) else structured
    for item in result.get("content", []):
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except (KeyError, ValueError):
                return item.get("text")
    raise AssertionError(f"No tool output: {result}")


def call(name, args):
    return unwrap(rpc("tools/call", {"name": name, "arguments": args}))


def must(condition, message):
    if not condition:
        raise AssertionError(message)


def legacy_protocol():
    result = rpc("initialize", {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "arquimedes-interop-smoke", "version": "1.0"},
    })
    must("serverInfo" in result, "Missing serverInfo")
    return {"server": result["serverInfo"].get("name"), "version": result.get("protocolVersion")}


def discover_public():
    status, data = request("/public-mcp", headers={"Accept": "application/json"})
    must(status == 200 and data.get("auth") == "none", f"Unexpected discovery: {status}, {data}")
    return data.get("transport")


def list_tools():
    tools = rpc("tools/list")["tools"]
    names = {tool["name"] for tool in tools}
    missing = EXPECTED[TARGET] - names
    must(not missing, f"Missing tools: {sorted(missing)}")
    must(not (names & DANGEROUS), f"Private tools leaked: {sorted(names & DANGEROUS)}")
    for tool in tools:
        must(isinstance(tool.get("inputSchema"), dict), f"Missing inputSchema: {tool['name']}")
    return sorted(names)


def private_is_protected():
    status, data = request("/mcp", {
        "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}
    })
    must(status == 401, f"Private endpoint without token returned HTTP {status}: {str(data)[:150]}")
    return "HTTP 401"


def domain_cases():
    if TARGET == "eap":
        evidence = call("avaliar_evidencia_eap", {"itens": [{
            "quantidade": 12, "produtividade": 3, "fonte": "caso-sintetico",
            "responsavel": "engenheiro", "criterio_aceite": "inspecao",
        }]})
        must(evidence["total"] == 1 and not evidence["lacunas"], f"Evidence failed: {evidence}")
        tree = call("validar_estrutura_eap", {"nos": [
            {"eap_id": "1", "parent_id": None, "nivel": 1},
            {"eap_id": "1.1", "parent_id": "1", "nivel": 2},
        ]})
        must(tree["ok"] and tree["total_nos"] == 2, f"Tree failed: {tree}")
        invalid = call("validar_estrutura_eap", {"nos": [
            {"eap_id": "1", "parent_id": "1", "nivel": 1},
        ]})
        must(not invalid["ok"], "Self-parent validation silently accepted")
        return "Evidence, hierarchy and invalid parent verified"
    if TARGET == "cronograma":
        duration = call("calcular_duracao_com_evidencia", {
            "quantidade": 12, "produtividade": 3,
            "unidade": "m2", "unidade_produtividade": "m2",
        })
        must(duration["duracaoDias"] == 4, f"Unexpected duration: {duration}")
        activities = [{"id": "A", "duracao_dias": 3},
                      {"id": "B", "duracao_dias": 2},
                      {"id": "C", "duracao_dias": 1}]
        deps = [{"predecessora_id": "A", "sucessora_id": "B", "tipo": "TI"},
                {"predecessora_id": "B", "sucessora_id": "C", "tipo": "TI"}]
        cpm = call("calcular_cpm_com_evidencia", {"atividades": activities, "dependencias": deps})
        must(cpm["duracao_projeto_dias"] == 6, f"Unexpected CPM duration: {cpm}")
        must(set(cpm["caminho_critico"]) == {"A", "B", "C"}, f"Wrong critical path: {cpm}")
        return "Duration=4, CPM=6, critical A-B-C verified"
    if TARGET == "gantt_lob":
        teams = call("dimensionar_equipes_lob", {"tempo_unitario": 6, "ritmo_desejado": 2})
        must(teams["numero_equipes"] == 3, f"Wrong teams: {teams}")
        activities = [{"nome": "A", "tempo_unitario": 6},
                      {"nome": "B", "tempo_unitario": 4}]
        balance = call("balancear_ritmos_lob", {"atividades": activities})
        must(balance["sugestoes"][1]["risco_interferencia"] is True, f"Risk not detected: {balance}")
        lob = call("calcular_linha_balanco", {
            "atividades": activities, "unidades": ["Casa 1", "Casa 2", "Casa 3"],
            "data_inicio": "2026-10-01",
        })
        must(lob["duracao_total_dias"] == 22, f"Wrong LOB duration: {lob}")
        must(lob["atividades"][1]["espera_total_dias"] == 4, f"Wrong waiting time: {lob}")
        must(lob["atividades"][0]["unidades"][0]["data_inicio"] == "2026-10-01", "Wrong start date")
        themes = call("listar_temas", {})
        must(isinstance(themes, list) and len(themes) == 8, f"Wrong themes: {themes}")
        return "Teams=3, LOB=22d, waiting=4d, 8 themes verified"
    raise ValueError(f"Unsupported target {TARGET!r}")


def modern_request(method, params=None, *, tool_name=None):
    meta = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {
            "name": "arquimedes-interop-smoke", "version": "1.0",
        },
    }
    p = dict(params or {})
    p["_meta"] = meta
    headers = {"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": method}
    if tool_name is not None:
        headers["Mcp-Name"] = tool_name
    payload = {"jsonrpc": "2.0", "id": 2, "method": method, "params": p}
    return request("/public-mcp", payload, headers=headers)


def probe_modern():
    global MODERN
    status, result = modern_request("server/discover")
    if status != 200 or not isinstance(result.get("result"), dict):
        return {"supported": False, "http_status": status,
                "error": str(result.get("error", ""))[:200]}
    try:
        status, listed = modern_request("tools/list")
        must(status == 200 and "result" in listed, f"Modern tools/list failed: {status}, {listed}")
        names = {t["name"] for t in listed["result"]["tools"]}
        must(EXPECTED[TARGET] <= names, f"Modern tool inventory incomplete: {sorted(names)}")
        name, arguments = {
            "eap": ("validar_estrutura_eap", {"nos": [
                {"eap_id": "1", "parent_id": None, "nivel": 1}]}),
            "cronograma": ("calcular_duracao_com_evidencia", {
                "quantidade": 12, "produtividade": 3, "unidade": "m2",
                "unidade_produtividade": "m2"}),
            "gantt_lob": ("dimensionar_equipes_lob", {
                "tempo_unitario": 6, "ritmo_desejado": 2}),
        }[TARGET]
        status, response = modern_request("tools/call", {
            "name": name, "arguments": arguments}, tool_name=name)
        must(status == 200 and "result" in response, f"Modern tools/call failed: {status}, {response}")
        value = unwrap(response["result"])
        expected = {"eap": ("ok", True), "cronograma": ("duracaoDias", 4),
                    "gantt_lob": ("numero_equipes", 3)}[TARGET]
        must(value.get(expected[0]) == expected[1], f"Modern calculation failed: {value}")
    except Exception as exc:
        return {"supported": False, "http_status": status, "error": str(exc)[:250],
                "phase": "modern_tools"}
    MODERN = True
    return {"supported": True, "http_status": 200,
            "verified": ["server/discover", "tools/list", "tools/call"]}


def main():
    if TARGET not in HOSTS:
        sys.exit("MCP_TARGET must be eap, cronograma or gantt_lob")
    record("public_discovery", discover_public)
    record("legacy_initialize", legacy_protocol)
    record("public_tools_list", list_tools)
    record("real_calculation_contracts", domain_cases)
    record("private_denies_anonymous", private_is_protected)
    # Only an observation until the server is upgraded to 2026-07-28.
    record("modern_2026_probe", probe_modern)
    report = {
        "server": TARGET, "origin": ROOT,
        "protocol_2026_07_28_supported": MODERN, "checks": CHECKS,
    }
    path = Path(os.getenv("MCP_REPORT_PATH", "mcp-interop-report.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed = [c["check"] for c in CHECKS if c["status"] == "fail"]
    if os.getenv("MCP_REQUIRE_MODERN") == "1" and not MODERN:
        failed.append("modern_protocol_not_yet_supported")
    print(json.dumps({"server": TARGET, "modern": MODERN, "failed": failed}), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
