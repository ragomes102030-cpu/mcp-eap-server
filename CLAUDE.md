# CLAUDE.md — mcp-eap-server

Regras de agente (Claude Code / Cline) para o **MCP de EAP** de obras de
construção civil. Leia antes de trabalhar neste diretório.

## O que é este projeto

Servidor **MCP (Model Context Protocol)** HTTP/streamable que expõe a EAP
(Estrutura Analítica do Projeto) de uma obra: nós hierárquicos com `EAP_ID`
no formato `1.2.3`, `PARENT_ID`, `NIVEL`, `PROJECT_ID`, `FRENTE_ID`,
`LOCAL_ID`, `TIPO_FRENTE`, `NOME`, `UNIDADE` e `QUANTIDADE`.

Stack: Python 3.11+, **FastMCP** (`mcp`), Pydantic v2, Uvicorn/Starlette,
SQLite local com fallback para **Turso/libSQL** em produção.

## Arquitetura (Fase 1)

| Arquivo | Papel |
|---|---|
| `models.py` | Camada de dados: schema, DAO, árvore, validação, migração e idempotência |
| `schemas.py` | Schemas Pydantic de entrada/saída |
| `server.py` | FastMCP: 11 tools, wrapper de erro `_seguro`, idempotência e seeds |

**Camadas rígidas**: `server.py` (apresentação MCP) nunca toca SQL direto;
`models.py` (dados) nunca importa `mcp`/`schemas`. Mantenha essa separação.

## Ferramentas expostas (13)

- **Projetos (obras)**: `criar_projeto`, `atualizar_projeto`, `listar_projetos`, `deletar_projeto`
- **Estrutura**: `criar_eap_node`, `get_eap_tree`, `get_eap_node`, `validar_estrutura`
- **Manutenção**: `atualizar_eap_node`, `deletar_eap_node`, `mover_eap_node`
- **Consulta**: `listar_por_tipo_frente`, `listar_templates`

**Projeto = obra**: toda tool de nó aceita `project_id` opcional (padrão
`default`). Operações são **escopadas ao projeto** (isolamento total entre
obras, inclusive `eap_id` repetidos em obras diferentes). Metadados da obra
(nome, tipo_obra, área, método, região, cliente) vivem na tabela `eap_project`.

## Regras de integridade (NÃO violar)

- **PK composta** `(project_id, eap_id)`. Nunca usá-los como PK simples global.
- **Unidade** em vocabulário fechado: `m², m³, ml, un, kg, conj, vb, pt`, sempre
  normalizada (`m2`→`m²`) via `normalizar_unidade`.
- **tipo_frente** em vocabulário fechado: `projeto, preliminares, fundacao,
  estrutura, alvenaria, cobertura, instalacoes, esquadrias, revestimento,
  pintura, acabamento, infraestrutura, paisagismo`. Normalizar e **rejeitar**
  valores fora — nunca gravar `tipo_frente` livre. Usar `normalizar_tipo_frente`.
- **Quantidade** só é permitida em **nós-folha** (sem filhos). `validar_estrutura`
  audita dupla contagem.
- **Hierarquia**: `nivel = pai.nivel + 1` (1 para raiz). `EAP_ID` deriva da posição.
- **Movimento**: `mover_eap_node` move nó + subárvore reenumerando `EAP_ID`/`NIVEL`
  (ex.: `1.2`→sob `2.1` vira `2.1.x`) e bloqueia ciclos (destino = próprio nó ou descendente).
- **Idempotência**: tools de escrita aceitam `request_id` opcional; reenvio do
  mesmo `request_id` devolve cache, não reexecuta.
- **Migração**: bancos antigos (PK simples) devem ser migrados para PK composta.
  Em Turso antigo, migre manualmente (não assumir automático).

## Nomenclatura interna (importante)

- Códigos/identificadores em ASCII sem acento: `fundacao` (não "fundação"),
  `instalacoes`, `hidrossanitaria`. No **nome** (descrição legível) pode ter acento.
- pt-BR para variáveis/mensagens/strings de negócio. Mantenha consistência com o
  que já existe (`eap_id`, `parent_id`, `nivel`, `tipo_frente`, `listar_filhos`).

## Verificação (todas as mudanças)

- **Prova por teste de evidência**, nunca por prosa. Antes de declarar algo feito,
  rode e mostre a saída real.
- Testar a camada de dados com `python -c`/script em DB temporário (remover o
  `eap.db` antes; ele é efêmero e não versionado — `.gitignore`).
- Validar o servidor de verdade: `python server.py` e handshake MCP
  (`initialize` → 200) ou `call_tool` das tools via `server.mcp._tool_manager`.
- Após mudanças, sempre `python -m py_compile models.py schemas.py server.py`.
- Cobertura mínima sugerida: criar→atualizar→get→deletar→validar + idempotência +
  migração.

## Escopo (Fase 1 vs Fase 2) — NÃO misturar

- **Fase 1 (aqui)**: dados da EAP, CRUD, árvore, validação, idempotência, templates
  como **referência histórica** (só consulta).
- **Fase 2 (futuro)**: sugeridor/inferência de EAP a partir dos templates, orçamento,
  quantitativos. Não adicione lógica de sugestão no `server.py`/`models.py` ainda.

Arquivos `orquestrador.py`, `diag_map.py`, `diag_p0.py` são **rascunhos de Fase 2**,
fora do versionamento — não os edite nem os includa em commits nesta Fase 1.

## Pontos de atenção

- **Não fechar conexões no meio do padrão** `with _connect() as conn:` + 
  `cursor.fetch*()` fora do `with` (quebraria no sqlite3). Evite regressões aí.
- `listar_projetos`/`listar_templates` devem devolver **dict** (não `sqlite3.Row`)
  para serialização JSON válida.
- `eap.db` não é versionado: sempre apague antes de rodar testes "limpos".
- Commit em pt-BR, mensagem descrevendo o item (ex.: `B1`, `I5`, `S2`).
- Mantenha o ponto de restauração: se o `server.py` sumir/regredir, recupere via
  `git checkout restore-fase1-pre-* -- server.py` ou do `__restore_*`.

## Roadmap pendente (não feito)

1. Soft-delete (`ativo`) + `eap_id_history` para auditoria de rebaixamento/movimento.
2. `nivel_confianca` (herdado pai→filho).