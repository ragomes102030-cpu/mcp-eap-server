# Arquimedes — contrato mínimo de interoperabilidade (proposta v1)

**Estado:** proposta/adaptador de borda; NÃO altera endpoints MCP existentes,
bancos de dados, validação cruzada ou semântica temporal em produção.

## Campos canônicos (JSON)
- `schema_version`: "1.0" (formato da mensagem; não altera o protocolo MCP).
- `calculation_version`: versão do algoritmo do motor produtor, registrada pelo orquestrador.
- `project_id`: string opaca; nunca reutilizar IDs entre obras.
- `eap_uid`: UID permanente do pacote; `eap_codigo` é atributo de apresentação mutável.
- `activity_id`: ID estável da atividade; `eap_uid` opcional quando cronograma usado isoladamente.
- `location_id`: ID imutável do local; ordem de execução é explicitamente fornecida.
- `quantity`: número finito não negativo; `unit` unidade canônica e rastreável.
- `duration`: número finito não negativo em dias corridos relativos; durações >0 para atividades não marco.
- `start_date` / `finish_date`: ISO 8601; **intervalo semiaberto** [início, término) em dias relativos, sem confundir dia civil com dia útil.
- `calendar_id`: ID/versão de calendário, se aplicado; `null` significa nenhum calendário.
- `baseline_id`: ID estável do snapshot aprovado, nunca sobrescrito.
- `source`: qual motor/usuário calculou; `assumptions`: lista explícita de premissas; `persisted`: boolean.

## Adaptadores e políticas (sem novas dependências entre MCPs)
1. Adaptador de **EAP**: mapa `uid -> eap_uid`, `eap_id -> eap_codigo`, preserva `project_id`.
2. Adaptador de **Cronograma**: mapa `eap_ref -> eap_uid` somente quando resolvido contra snapshot EAP do **mesmo projeto**; códigos/IDs legados continuam aceitos e são sinalizados `unverified`, nunca inventados.
3. Adaptador de **Gantt/LOB**: converte datas e atividades já calculadas; `nome`, `secao`, `data_inicio`, `data_fim_planejada` permanecem válidos. Mantém `activity_id` e `location_id` no envelope do orquestrador até o cliente exportador oferecer colunas específicas.
4. Se `calendar_id == null`, dados representam **dias corridos relativos**; não atribuir datas úteis automaticamente.
5. Se houver divergência entre cálculo interno e MCP, registrar diferenças, entradas, SHA, tolerância, versão e **exigir revisão humana**. Não substituir o valor oficial.
6. Ausência de qualquer MCP: retornar `BLOQUEADO` com causa/timeout, jamais sintetizar resultados.
7. Escrever no banco exige rota privada, autenticação e autorização explícita; por padrão usar **somente** as tools públicas sem persistência.
8. Reativação futura na Plataforma Obras: circuit breaker, timeout, fallback nos módulos internos, registro de origem e comparação em modo sombra; nenhuma ativação de produção nesta fase.

## Compatibilidade
Não remover/renomear `eap_id`, `eap_ref`, `duracao_dias`, `data_inicio`,
`data_fim`, `unidades` ou quaisquer campos/tipos MCP já publicados.
Mudanças adicionais devem ser **aditivas**. Validação de entrada mais estrita
pode rejeitar dados corruptos previamente aceitos; registrar em changelog.

## Critérios de aceitação antes de habilitar chamadas externas
Conferir no benchmark: cobertura do escopo de referência, preservação de UID,
rede CPM finita sem órfãos, quatro tipos de vínculo, folga livre, LOB sem
sobreposição da própria equipe, XLSX válido e tempos compatíveis. Não confundir
HTTP 200 com validação matemática. Nenhuma declaração de conformidade normativa.
