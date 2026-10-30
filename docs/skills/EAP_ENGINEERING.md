# Skill — EAP de engenharia (procedimento, não algoritmo)

**Quando usar:** decompor e auditar escopo; criar e revisar dicionário de pacotes.

**Entradas obrigatórias:** `project_id`, escopo contratado/referência com versão e fonte, locais, entregáveis, critério de aceite; identidades `eap_uid` devem sobreviver a mudanças no código da árvore.

**Tools MCP públicas:** `validar_estrutura_eap`, `avaliar_evidencia_eap` (stateless). **Privadas (somente após autorização):** `criar_eap_node`, `validar_estrutura`, `move_eap_node`, `validar_regra_100_porcento`, `listar_escopo`, demais operações de dicionário/escopo.

**Validações:** raiz coerente, pai imediato, sem órfãos/ciclos/duplicidades; quantidade exclusiva em folhas; UID permanente; regra de 100% exige cobertura contra escopo de referência, sem sobreposição de vínculos principais; projetos isolados.

**Revisão humana:** limites do escopo contratado, exclusões, responsabilidade, fonte dos quantitativos e critério de aceite. Não declarar aprovação sem documentação de referência.

**Erros bloqueantes:** escopo de referência ausente para declarar completude, vínculos principais ambíguos, UID em conflito, projeto cruzado ou estrutura inválida.

**Saída:** IDs estáveis, código hierárquico, itens cobertos/não cobertos, porcentagem, origem, SHA/versão, premissas, evidência e limitações. Não inventar serviços e não substituir algoritmo por LLM.
