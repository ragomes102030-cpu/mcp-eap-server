# MCP EAP Server

Servidor MCP (Model Context Protocol) de EAP (Estrutura Analítica do Projeto)
para obras de construção civil. Expõe 10 ferramentas via HTTP/streamable
para clientes MCP (Claude Desktop, VS Code, etc.).

## Ferramentas (10 tools)

### Estrutura
| Tool | Descrição |
|---|---|
| `criar_eap_node` | Cria nó hierárquico, gera EAP_ID (ex.: "1.2.3") e calcula NIVEL |
| `get_eap_tree` | Retorna a árvore completa ou subárvore em JSON aninhado |
| `get_eap_node` | Retorna os dados de um nó específico |
| `validar_estrutura` | Audita a árvore: órfãos, duplicidades, NIVEL, dupla contagem e coerência de tipo_frente |

### Manutenção
| Tool | Descrição |
|---|---|
| `atualizar_eap_node` | Atualiza campos de um nó (valida unidade e tipo_frente) |
| `deletar_eap_node` | Deleta nó (folha) ou subárvore inteira (`cascade=true`) |
| `listar_projetos` | Lista projetos e a contagem de nós de cada um |
| `deletar_projeto` | Remove todas as EAPs de um projeto (irreversível) |

### Consultas e referência
| Tool | Descrição |
|---|---|
| `listar_por_tipo_frente` | Filtra nós por tipo de frente de serviço (ex.: fundacao, estrutura) |
| `listar_templates` | Lista templates de EAP reais (referência histórica de orçamento) |

## Como rodar localmente

```bash
pip install -r requirements.txt
python server.py            # porta padrão 10000
# ou
uvicorn server:app --host 0.0.0.0 --port 10000
```

O servidor expõe o endpoint em `http://localhost:10000/mcp`.

## Schema do nó (ARES)

- `project_id`: identificador do projeto (PK composta com `eap_id`)
- `eap_id`: código hierárquico gerado (ex.: "1.2.3")
- `parent_id`: auto-referência (NULL = raiz)
- `nivel`: nível armazenado (INTEGER, `pai.nivel + 1`)
- `frente_id`, `local_id`, `tipo_frente`, `nome`, `unidade`, `quantidade`

### Regras de integridade
- **PK composta** `(project_id, eap_id)` — permite várias obras sem colidir códigos.
- **Unidade** em vocabulário fechado (`m², m³, ml, un, kg, conj, vb, pt`), normalizada
  na entrada (`m2` → `m²`).
- **tipo_frente** em vocabulário fechado (`fundacao, estrutura, alvenaria, cobertura,
  instalacoes, esquadrias, revestimento, pintura, acabamento, ...`), normalizado e validado.
- **Quantidade** só permitida em nós-folha (auditado por `validar_estrutura`).

### Migração automática
Na inicialização, o servidor detecta bancos SQLite no regime antigo (PK simples em `eap_id`)
e os **migra** automaticamente para a PK composta, preservando os dados (atribui
`project_id='default'` aos nós antigos). Bancos **Turso/libSQL novos** já nascem com a
PK composta. Se você reutilizar um database Turso antigo, aplique o novo SCHEMA
manualmente antes do deploy.

## ⚠️ Aviso importante sobre o SQLite

O banco padrão é um arquivo SQLite local (`eap.db`). Em ambientes como o Render,
o sistema de arquivos é **efêmero** — dados são perdidos a cada redeploy. Configure
`TURSO_URL`/`TURSO_TOKEN` para usar Turso/libSQL persistente em produção.

Para migrar um banco criado antes desta versão (PK simples), basta subir o servidor:
a migração é aplicada automaticamente ao primeiro `init_db()`.

## Deploy no Render

1. Conecte o repositório GitHub
2. Build: `pip install -r requirements.txt`
3. Start: `uvicorn server:app --host 0.0.0.0 --port $PORT`
4. (O `Procfile` já contém o comando de start)

Para persistência, defina `TURSO_URL` e `TURSO_TOKEN` nas variáveis de ambiente.
