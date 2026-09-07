# Análise de buracos da EAP — Fase 1 fechada (2026-09-08)

Estado de referência vivo: `https://mcp-eap-server.onrender.com/mcp` — 2 projetos,
**36 nós** (default 10 + casa-terreno-50m2 26), `validar_estrutura` **0 problemas**
nos dois com `strict_single_root` ligado (que já é o default do servidor).

## 1. Buracos encontrados no estado pré-Fase 1 (33 nós)

**default (9 nós, seed Piemarta):**
- 2 raízes (`1 FUNDAÇÕES`, `2 ESTRUTURA`) — sem nó-obra `[projeto]`;
- `1.2 VIGAS BALDRAME` tipo `estrutura` sob pai `fundacao` (e seu filho
  `1.2.1 CONCRETO VIGAS` idem) — divergência de classificação;
- nomes em CAIXA ALTA (aviso semântico, legado).

**casa-terreno-50m2 (24 nós):**
- **9 raízes** (1..9), nenhuma delas nó-obra;
- ~15 folhas **fantasmas**: sem `unidade`/`quantidade` (não mensuráveis);
- `FRENTE_ID`/`LOCAL_ID` vazios em todos os nós;
- tipo `instalacoes` **fora do vocabulário fechado**;
- filhos herdando tipo do pai — coerente, mas agrupado sob `instalacoes`.

## 2. Decisões tomadas (e onde estão registradas)

1. **Raiz única por projeto**: obra = nó tipo `projeto` no topo; tudo abaixo dele.
   Implementado em F1.2 (`migrar_raiz_unica.py`, `criar_projeto` já cria a raiz).
2. **Vocabulário fechado — split de `instalacoes`**: oficializada a divisão
   `eletrica` / `hidrossanitaria`; `instalacoes` deixou de ser válido
   (F1.2b). Esta decisão é a exigida pelo §3 do prompt e fica registrada AQUI.
3. **Baldrame é fundação**: correção de classificação legada (dado, não schema):
   `VIGAS BALDRAME` e `CONCRETO VIGAS` do default → `fundacao`.
4. **Retrabalho tipado como irmão R{n}** (F1.6): `status=retrabalho`,
   `revisao`, `motivo` obrigatório, `origem_uid` linkando ao original;
   original nunca alterado; R não conta como duplicidade nem viola folha/qtd.
5. **`resumo_quantitativos` agrupa por `(tipo_frente, unidade)`** (F1.5):
   nunca mistura unidades; só folhas; `null` ignorado; `0` conta como folha.
6. **Busca normalizada acento+caixa** (`buscar_eap_node`, F2.3 antecipada):
   `escavacao` acha `ESCAVAÇÃO`.
7. **Export P6/MS Project (F2.5) adiado**: a prova de integridade do Passo 7
   do aceite foi feita via backup em 2 camadas (cópia física do DB + dump
   lógico csv/json em `backup/`).

## 3. O que mudou nos dados (local → produção)

| Passo | default | casa-terreno-50m2 |
|---|---|---|
| Pré | 9 nós, 2 raízes, 1 problema (divergência) | 24 nós, 9 raízes, 1 problema (multi-raiz) |
| Migração | + nó-obra `3` "Piemarta (exemplo)" `[projeto]`; `1`→`3.1`, `2`→`3.2` (uids preservados, `eap_id_history` gravado) | reconstruída do seed canônico (delete + recreate): 26 nós, raiz única |
| Correção de dado | `3.1.2` e `3.1.2.1` → `fundacao` | — (seed já nasce coerente) |
| Normalização | — | folhas com unidade/quantidade (m³, m², un, pt, ml, kg), `LOCAL_ID=TERREO-GERAL`, split elétrica(1.6)/hidrossanitaria(1.7) |
| Pós | **10 nós, 0 problemas** | **26 nós, 0 problemas** |

Nota: os uids antigos da casa morreram no rebuild — preservados no backup
em 2 camadas (`backup/eap_pre_migracao_*.db` + `backup/backup_*.csv|json`).
O default foi migrado in-place (uids preservados) porque é o projeto de
referência das baterias.

## 4. Buracos que continuam abertos (Fase 2)

- **F2.4** Código CSI + composição SINAPI + `resumo_custo`;
- **F2.5** `exportar_eap` (csv/xer/mpp_json) + import (round-trip);
- F2.1/F2.2/F2.3* do prompt original conforme escopo aprovado
  (F2.3 busca já antecipada e entregue);
- CAIXA ALTA do default permanece como **aviso** (legado histórico, não bloqueia).
