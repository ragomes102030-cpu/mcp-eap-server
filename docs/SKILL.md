# SKILL — MCP EAP Server (EAP/WBS de obras)

## 1. O que é
Servidor MCP para manter a EAP (Work Breakdown Structure) de obras:
hierarquia de pacotes, quantitativos por unidade, donos e critérios de
medição, retrabalho tipado e auditoria de renumeração.

## 2. Conexão
- Ao vivo: `https://mcp-eap-server.onrender.com/mcp` (HTTP streamable).
- Local: `python server.py` e conectar em `http://127.0.0.1:<PORTA>/mcp`.

## 3. Tools (18)
`criar_eap_node`, `atualizar_eap_node`, `deletar_eap_node`, `move_eap_node`,
`get_eap_node`, `get_eap_tree`, `validar_estrutura`, `resumo_quantitativos`,
`listar_por_tipo_frente`, `buscar_eap_node`, `criar_projeto`,
`atualizar_projeto`, `deletar_projeto`, `listar_projetos`, `listar_templates`,
`definir_criterio`, `pacotes_sem_dono`, `registrar_retrabalho`.

## 4. Modelo de dados
- `uid` (uuid4, estável) é a referência externa; `EAP_ID` (`1.2.3`) é só
  display e muda em movimentação — cada move grava em `eap_id_history`
  (get por eap_id antigo devolve o nó atual com `movido_de/para`).
- Tudo escopa por `project_id` (obra). `criar_projeto` já cria a raiz da obra
  (nó tipo `projeto`, nível 1) — projeto tem **raiz única**.
- Quantidade/unidade só em folha. `nao_aplicavel+motivo_na` marca pacote N/A.
- Retrabalho = irmão `R{n}` do original (`status=retrabalho`, `revisao`,
  `motivo` obrigatório, `origem_uid`); original nunca é alterado.

## 5. Regras de integridade (validar_estrutura)
`problemas[]` (invalidam a árvore): `EAP_ID` duplicado, nó órfão, `NIVEL`
inconsistente, quantidade em não-folha, filho divergente de `tipo_frente`
(nível ≥ 2) e `MULTI_ROOT` quando `strict_single_root` ligado (**default de
produção desde o fechamento da Fase 1**; passar `strict_single_root=False`
para auditar legado). `avisos[]` (não invalidam): CAIXA ALTA, agregador com
unidade, divergência no nível 2, `FILHO_UNICO`, `UNIDADE_INCOMPATIVEL`
(matriz pai×filho), `FANTASMA` (folha sem qtd e sem N/A), `SEM_DONO`.

## 6. Vocabulário fechado
- Unidades: `m², m³, ml, un, pt, vb, conj, kg` (entrada normaliza `m2/m3`).
- `tipo_frente`: `projeto, preliminares, fundacao, estrutura, alvenaria,
  cobertura, eletrica, hidrossanitaria, esquadrias, revestimento, pintura,
  acabamento`. **`instalacoes` foi descontinuado** — split em
  `eletrica`/`hidrossanitaria` (decisão registrada em `docs/analise_buracos_eap.md`).

## 7. Busca e quantitativos
- `buscar_eap_node(termo)`: substring ignorando acento e caixa
  (`escavacao` acha `ESCAVAÇÃO`), sobre nome/eap/frente/local/responsável.
- `resumo_quantitativos`: agrupa folhas por `(tipo_frente, unidade)`;
  nunca soma unidades diferentes; `null` ignorado; `0` conta como folha;
  separa `previsto` × `retrabalho`.

## 8. Idempotência
Tools de escrita aceitam `request_id`: reenvio com o mesmo id devolve a
mesma resposta sem duplicar (camada de serviço via `verificar/salvar_idempotencia`).

## 9. Operação
- **Env**: `PORT`; `TURSO_URL`/`TURSO_TOKEN` (produção persistente — sem
  Turso usa `eap.db` local efêmero); `EAP_STRICT_SINGLE_ROOT` (`1` é o
  default; `0` só para roteiros legados multi-raiz).
- **Baterias locais**: `python -m pytest tests/ -q` (suite; o conftest já
  isola os roteiros A/B), `_teste_planejamento.py` e `_teste_multiprojeto.py`
  (MCP real em porta efêmera) — rodar com `EAP_STRICT_SINGLE_ROOT=0`.
- **Migração**: colunas novas são auto-migradas no boot (idempotente,
  inclusive em Turso); recriação de tabela multi-projeto NÃO roda em Turso
  (bancos novos já nascem no schema atual).
- **Backup**: cópia física do DB + dump lógico csv/json em `backup/`
  (ver `_backup_dump.py`); estado pré-Fase 1: 33 nós (9 default + 24 casa).
- **Deploy**: push em `master` dispara Render; smoke pós-deploy com
  `validar_estrutura` (0 problemas nos 2 projetos) e contagem de tools (18).

## 10. Estado de referência (pós-Fase 1, 2026-09-08)
2 projetos · 36 nós (default 10, casa-terreno-50m2 26) · 0 problemas.
Histórico e evidências: `docs/relatorio_fase1_fase2.md`.
