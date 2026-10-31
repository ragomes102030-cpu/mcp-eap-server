# Contrato EAP Arquimedes v1 — compatibilidade independente

## Objetivo
A Plataforma Obras funciona integralmente sem MCP. O MCP EAP funciona sem Plataforma Obras e pode atender ChatGPT, Claude e outros clientes. Este contrato e uma **camada de interoperabilidade**, nao um banco compartilhado nem uma migracao das ferramentas existentes.

## Referencias verificadas na Plataforma Obras
- `docs/EAP-POLITICA-DECOMPOSICAO.md`: profundidade adaptativa; grupo pode ter filhos; pacote e entrega sao terminais; regra dos 100% exige revisao de escopo.
- `server/construction/eap-validator.ts`: validacao estrutural e de escopo.
- `server/construction/eap-approval-validator.ts`: aprovacao distinta de readiness de baseline.
- `server/construction/versioned-wbs.ts`: IDs internos mudam entre versoes; codigo e identidade de correspondencia no contexto da obra/versao.
- `server/construction/eap-proposal-apply.ts`: propostas aplicadas em versao de trabalho com verificacao posterior.

## Contrato minimo de intercambio
```json
{
  "projectRef": "OB-EXEMPLO",
  "versionRef": "plano-v1",
  "nodes": [
    {"code": "1", "parentCode": null, "name": "Obra", "nodeType": "grupo", "level": 1},
    {"code": "1.1", "parentCode": "1", "name": "Fundacoes", "nodeType": "pacote", "level": 2,
     "decompositionBasis": "discipline", "description": "Escopo conhecido",
     "inclusions": "Servicos definidos", "exclusions": "Servicos fora do contrato",
     "responsible": "Engenheiro", "acceptanceCriteria": "Conforme projeto"}
  ]
}
```

Chave de intercambio: `projectRef + versionRef + code`. Nunca usar IDs internos de banco como identidade universal. Campos `location`, `unit`, `plannedQuantity` sao opcionais. Localizacao e dimensao de planejamento, nao nivel obrigatorio.

## Validade e evidencias
- `structural_valid`: testa raiz unica, codigos, hierarquia, pais, tipos terminais e bases de decomposicao.
- `scope_coverage_verified`: **sempre false nesta primeira implementacao**. O contrato nao inventa cobertura de 100%; exige evidencias documentais e analise semantica posterior.
- Aprovacao e baseline **nao sao realizadas** por esta biblioteca.
- Alertas nao sao equivalentes a erro bloqueante. A politica de aprovacao e um fluxo separado.

## Compatibilidade
`arquimedes_eap_contract.py` nao altera `server.py`, `schemas.py`, tabelas, dados nem ferramentas MCP publicas. Ele pode ser chamado por futuras ferramentas de exportacao/auditoria e pelo conjunto de testes. Nenhuma sincronizacao automatica com a Plataforma Obras esta habilitada.

## Testes
```bash
python -m unittest -v test_arquimedes_eap_contract.py
```
Os testes sao locais e nao usam banco. Antes de merge/deploy, executar a suite e comparar os casos com o validador nativo da Plataforma Obras.

## Evolucao necessaria
1. Mapear todos os campos reais do dicionario MCP e seus equivalentes na Plataforma Obras.
2. Criar adaptador de leitura sem alterar contratos legados.
3. Homologar regras dos 100% com corpus de escopos e casos de sobreposicao.
4. Definir operacoes de versao e aprovacao, sem escrita cruzada automatica.
5. Somente depois expor ferramentas novas e publicar em producao.
