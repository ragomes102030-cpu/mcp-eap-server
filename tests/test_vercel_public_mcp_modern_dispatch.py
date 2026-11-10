from api.public_mcp import _dispatch_modern_jsonrpc


def test_modern_discover_and_tools_list_are_json_values():
    discover = _dispatch_modern_jsonrpc({"jsonrpc": "2.0", "id": 1,
                                         "method": "server/discover", "params": {}})
    assert "2026-07-28" in discover["result"]["supportedVersions"]
    listed = _dispatch_modern_jsonrpc({"jsonrpc": "2.0", "id": 2,
                                        "method": "tools/list", "params": {}})
    tools = listed["result"]["tools"]
    assert {tool["name"] for tool in tools} == {
        "avaliar_evidencia_eap", "validar_estrutura_eap", "propor_eap_por_prompt"
    }
    assert all("inputSchema" in tool for tool in tools)


def test_modern_tool_call_runs_stateless_public_validation():
    response = _dispatch_modern_jsonrpc({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "validar_estrutura_eap",
                   "arguments": {"nos": [{"eap_id": "1", "parent_id": None, "nivel": 1}]}},
    })
    result = response["result"]
    assert result["structuredContent"]["ok"] is True
    assert result["structuredContent"]["persistido"] is False
    assert result["content"][0]["type"] == "text"


def test_modern_unknown_method_is_json_rpc_method_error():
    response = _dispatch_modern_jsonrpc({"jsonrpc": "2.0", "id": 4,
                                         "method": "not/a/method", "params": {}})
    assert response["error"]["code"] == -32601
