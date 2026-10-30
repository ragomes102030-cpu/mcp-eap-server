"""In-process regression: same public MCP endpoint must serve legacy and 2026 clients.

Run with MCP_TARGET=eap|cronograma.
No production credentials, network calls or project mutations are involved.
"""
import os
import unittest
from starlette.testclient import TestClient
from api.index import app

TARGET = os.environ["MCP_TARGET"]
HOSTS = {
    "eap": "https://arquimedes-mcp-eap.vercel.app",
    "cronograma": "https://arquimedes-mcp-cronograma.vercel.app",
}
EXPECTED = {
    "eap": {"avaliar_evidencia_eap", "validar_estrutura_eap"},
    "cronograma": {"calcular_duracao_com_evidencia", "calcular_cpm_com_evidencia"},
}


def meta():
    return {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {
            "name": "dual-protocol-ci", "version": "1.0.0",
        },
    }


def decode_tool(res):
    assert not res.get("isError"), res
    data = res.get("structuredContent")
    if isinstance(data, dict):
        return data.get("result", data)
    for block in res.get("content", []):
        if block.get("type") == "text":
            import json
            try:
                value = json.loads(block["text"])
                return value.get("result", value) if isinstance(value, dict) else value
            except ValueError:
                return block["text"]
    raise AssertionError(f"Missing tool result: {res}")


class TestDualProtocol(unittest.TestCase):
    def rpc(self, client, method, params, modern=False, tool_name=None):
        headers = {"Accept": "application/json, text/event-stream",
                   "Content-Type": "application/json"}
        if modern:
            params = dict(params)
            params["_meta"] = meta()
            headers["MCP-Protocol-Version"] = "2026-07-28"
            headers["Mcp-Method"] = method
            if tool_name:
                headers["Mcp-Name"] = tool_name
        response = client.post("/public-mcp",
            json={"jsonrpc": "2.0", "id": 42, "method": method, "params": params},
            headers=headers)
        self.assertEqual(response.status_code, 200, response.text[:800])
        payload = response.json()
        self.assertIn("result", payload, payload)
        return payload["result"]

    def test_legacy_and_modern(self):
        with TestClient(app, base_url=HOSTS[TARGET]) as client:
            get = client.get("/public-mcp", headers={"Accept": "application/json"})
            self.assertEqual(get.status_code, 200, get.text[:400])
            self.assertTrue(get.json().get("ok"))
            legacy = self.rpc(client, "initialize", {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "ci-legacy", "version": "1.0.0"},
            })
            self.assertIn("serverInfo", legacy)
            legacy_tools = self.rpc(client, "tools/list", {})
            self.assertEqual({t["name"] for t in legacy_tools["tools"]}, EXPECTED[TARGET])
            modern = self.rpc(client, "server/discover", {}, modern=True)
            self.assertIn("2026-07-28", modern.get("supportedVersions", []))
            modern_tools = self.rpc(client, "tools/list", {}, modern=True)
            self.assertEqual({t["name"] for t in modern_tools["tools"]}, EXPECTED[TARGET])
            if TARGET == "eap":
                name = "validar_estrutura_eap"
                args = {"nos": [{"eap_id": "1", "parent_id": None, "nivel": 1}]}
                key, expected = "ok", True
            else:
                name = "calcular_duracao_com_evidencia"
                args = {"quantidade": 12, "produtividade": 3,
                        "unidade": "m2", "unidade_produtividade": "m2"}
                key, expected = "duracaoDias", 4
            for modern_mode in (False, True):
                with self.subTest(modern=modern_mode):
                    result = decode_tool(self.rpc(client, "tools/call",
                        {"name": name, "arguments": args},
                        modern=modern_mode, tool_name=name if modern_mode else None))
                    self.assertEqual(result[key], expected)
                    self.assertFalse(result.get("persistido", False))


if __name__ == "__main__":
    unittest.main()
