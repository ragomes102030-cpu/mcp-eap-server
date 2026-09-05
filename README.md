# MCP EAP Server

Servidor MCP (Model Context Protocol) de EAP (Estrutura Analítica do Projeto)
para obras de construção civil. Exponde 5 ferramentas via HTTP/streamable
para clientes MCP (Claude Desktop, VS Code, etc.).

## Ferramentas (5 tools)

| Tool | Descrição |
|---|---|
| `criar_eap_node` | Cria nó hierárquico, gera EAP_ID (ex.: "1.2.3") e calcula NIVEL automaticamente |
| `get_eap_tree` | Retorna a árvore completa ou subárvore em JSON aninhado |
| `get_eap_node` | Retorna os dados de um nó específico |
| `validar_estrutura` | Detecta órfãos, duplicidades de EAP_ID e NIVEL inconsistente |
| `listar_por_tipo_frente` | Filtra nós por tipo de frente de serviço (ex.: alvenaria, estrutura) |

## Como rodar localmente

```bash
# Instalar dependências
pip install -r requirements.txt

# Subir servidor (porta padrão 10000)
python server.py

# ou via uvicorn
uvicorn server:app --host 0.0.0.0 --port 10000
```

O servidor expõe o endpoint em `http://localhost:10000/mcp`.

## Schema do nó (ARES)

- `eap_id`: código hierárquico gerado (TEXT, PRIMARY KEY)
- `parent_id`: auto-referência (FK, NULL = raiz)
- `nivel`: nível armazenado (INTEGER)
- `frente_id`, `local_id`, `tipo_frente`, `nome`, `unidade`, `quantidade`

## ⚠️ Aviso importante sobre o SQLite

O banco de dados é um arquivo SQLite local (`eap.db`). Em ambientes como o
Render, o sistema de arquivos é **efêmero** — dados são perdidos a cada
redeploy. **Para uso em produção, troque o banco por PostgreSQL** (gratuito
no Render) antes de subir.

## Deploy no Render

1. Conecte o repositório GitHub
2. Build: `pip install -r requirements.txt`
3. Start: `uvicorn server:app --host 0.0.0.0 --port $PORT`
4. (O `Procfile` já contém o comando de start)
