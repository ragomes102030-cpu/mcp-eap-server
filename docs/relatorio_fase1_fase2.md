# Relatório Fase 1 / Fase 2 — mcp-eap-server

Data: 2026-09-08 · Servidor vivo: `https://mcp-eap-server.onrender.com/mcp`

## 1. Fase 1 — entregue (commits no master)

| Commit | Feature |
|---|---|
| `858fe31` | **F1.1** `uid` estável por nó + `eap_id_history` + get por uid/eap antigo |
| `576a6b9` | **F1.2a** erro `MULTI_ROOT` com flag `strict_single_root` |
| `d4efd66` | **F1.2b** split `eletrica`/`hidrossanitaria` (instalações depreciado), regra pai=projeto, `migrar_raiz_unica.py` + seeds canônicos |
| `f9c6d50` | **F1.2c** `criar_projeto` já cria a raiz da obra `[projeto]` |
| `64b26ec` | **F1.3** dicionário do pacote + dono/OBS (`descricao`, `criterio_medicao`, `responsavel`, `disciplina`), `definir_criterio`, `pacotes_sem_dono`, aviso `SEM_DONO` |
| `e730ac1` | **F1.4** folha mensurável/N-A (`nao_aplicavel`+`motivo_na`), aviso `FANTASMA`, normalização de nomes |
| `0c34c39` | **F1.5** matriz unidade pai×filho (`UNIDADE_INCOMPATIVEL`), `FILHO_UNICO`, `resumo_quantitativos` por `(tipo_frente, unidade)` |
| `1b2a7d7` | **F1.6** retrabalho tipado como irmão `R{n}` (`status`, `revisao`, `motivo` obrigatório, `origem_uid`; original intacto) |
| `ac6746d` | Passo 4: `STRICT_SINGLE_ROOT` **ligado por padrão** |
| `76709a5` | Testes do strict sem quebrar roteiros A/B legados (`conftest` força `EAP_STRICT_SINGLE_ROOT=0` nas baterias) |
| `55af4cd` | **F2.3 (antecipada)** `buscar_eap_node` — substring com acento/caixa ignorados; **18 tools** |

Total: **18 tools** no servidor (antes: 17).

## 2. Fechamento da Fase 1 — passos executados com validação

1. **Backup em 2 camadas** (decisão: opção B): cópia física do DB
   (`backup/eap_pre_migracao_20260907-140238.db`) + dump lógico csv/json
   dos 2 projetos — **33 nós** (`backup_default.csv`=9 + `backup_casa-terreno-50m2.csv`=24).
2. **Migração default (ensaio local)**: raiz-obra `3` "Piemarta (exemplo)"
   `[projeto]`, `1`→`3.1`, `2`→`3.2` (9→10 nós, uids preservados).
   Validação acusou 1 problema **pré-existente**: `1.2 estrutura` sob `1 fundacao`.
3. **Casa 50 (ensaio local)**: normalização + `LOCAL_ID=TERREO-GERAL` +
   split de instalações via seed canônico (26 nós).
4. **Strict ligado por padrão** (`ac6746d`); conftest isola os roteiros legados.
5. **Suite + aceite**: pytest **45 passed**; aceite §4 **8/8 PASS**
   (correção do Teste 4: `resumo_quantitativos` agrupa por
   `(tipo_frente, unidade)` — o 2.1.1 movido aparece no grupo `fundacao/m³`
   = 12.0, e não junto do `estrutura/m³` = 30.0; comportamento correto, a
   asserção original é que buscava grupo só por unidade).
6. **`buscar_eap_node` confirmado nas 18 tools** ao vivo e nas baterias MCP:
   planejamento **27 PASS / 0 FAIL**, multiprojeto **34 PASS / 0 FAIL**
   (rodar com `EAP_STRICT_SINGLE_ROOT=0`, igual ao conftest).
7. **Push + deploy + smoke ao vivo**: push `1f923ce..55af4cd` (12 commits);
   Render deployou (Turso persistente confirmado: 33 nós pré intactos pós-swap).
   Replicação dos passos 2-4 **em produção via MCP**:
   - default in-place: obra `3` criada, moves com uids preservados,
     correção de dado `3.1.2` **e** `3.1.2.1` → `fundacao`
     (baldrame e seu concreto são fundação — opção 1 autorizada);
   - casa: `deletar_projeto` + recreate fiel ao seed canônico (25 creates
     com EAP_ID conferido um a um);
   - **smoke final**: 18 tools · 2 projetos · **36 nós** ·
     `validar_estrutura` **0 problemas** nos 2 projetos **com e sem flag**
     (strict é default de produção) · busca `escavacao` → `ESCAVAÇÃO SAPATAS`.
8. **Docs**: `docs/analise_buracos_eap.md` (decisões §3, incl. split de
   `instalacoes`), este relatório, SKILL §5/§9.

## 3. Fase 2 — status

- **F2.3 busca**: **entregue antecipada** (`55af4cd`) — era pré-requisito do
  aceite nº 5.
- **F2.5 export**: **adiado** com ciência do usuário; a prova de integridade
  do aceite nº 7 foi feita pelo backup em 2 camadas. Fica para a Fase 2 junto
  do import (round-trip).
- **F2.4 CSI/SINAPI** e demais: pendentes (ver `docs/analise_buracos_eap.md` §4).

## 4. Evidência do smoke final (2026-09-08)

```
TOOLS: 18 (esperado 18)
PROJETOS: 2 / 36 nos (ESPERADO 36) OK
   casa-terreno-50m2: 26 nos
   default: 10 nos
[default] sem-flag: nos=10 problemas=0 valida=True | strict: problemas=0 valida=True
[casa-terreno-50m2] sem-flag: nos=26 problemas=0 valida=True | strict: problemas=0 valida=True
BUSCAR 'escavacao': total = 1 -> ['ESCAVAÇÃO SAPATAS']
RESUMO casa (grupos): [('acabamento','m²',202.0), ('alvenaria','m²',135.0),
 ('cobertura','m²',120.0), ('eletrica','pt',16.0), ('eletrica','un',1.0),
 ('esquadrias','un',10.0), ('estrutura','m³',1.2), ('fundacao','kg',210.0)]
```
