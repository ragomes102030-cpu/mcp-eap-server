# MCP EAP — contrato público, interoperabilidade e segurança

Data da revisão: 2026-11-09. A regra ampliada do dicionário mínimo e a cobertura explícita das unidades estão em validação local; não afirmar que a URL de produção já oferece essa regra antes de novo deployment e smoke.

## Como conectar um cliente MCP

- Transporte: **Streamable HTTP**.
- Endpoint público: `https://arquimedes-mcp-eap.vercel.app/public-mcp`.
- Autenticação: nenhuma; **somente cálculos/auditorias sem persistência**.
- Ferramentas anunciadas: **3: avaliar_evidencia_eap, validar_estrutura_eap, propor_eap_por_prompt**.
- Clientes não precisam de plugin específico de ChatGPT: a conexão é via protocolo MCP.
  A interface e o suporte a conectores HTTP variam entre aplicações.
- Um GET simples pode retornar JSON de diagnóstico. Isto **não substitui**
  `initialize` ou `server/discover`, `tools/list` e `tools/call`.

## Contrato de entrada — `avaliar_evidencia_eap`

`tools/list` publica um schema fechado por item. Os campos são opcionais para permitir auditoria parcial sem inventar evidências; campos desconhecidos são rejeitados. O avaliador reconhece os nomes canônicos em português e os aliases indicados:

- Quantidade: `quantidade`, `plannedQuantity` ou `quantity`.
- Produtividade: `produtividade` ou `productivity`.
- Fonte: `fonte` ou `source`; cada campo aceita texto ou lista de referências textuais.
- Cobertura de unidade: quantidade (`unidade` / `quantityUnit`) e produtividade (`unidade_produtividade` / `productivityUnit`) são contadas separadamente; ainda não se verifica dimensionalmente se as unidades são compatíveis entre si.
- Dicionário mínimo: código, descrição, critério de medição, localização e disciplina no dicionário; unidade, responsável e critério de aceitação podem estar no item ou no dicionário. Os aliases portugueses/ingleses são aceitos.
- Inclusões, exclusões e fontes aninhadas continuam disponíveis; a fonte também pode ser enviada na raiz. Campos desconhecidos são rejeitados.
- Marcadores de estado sem evidência (`PENDENTE`, `A CONFIRMAR`, `A DEFINIR`, `NAO_DECLARADA`, `SEM DADO`, `N/A` e aliases) não contam como campos preenchidos.
- `itens_com_lacunas` identifica cada item incompleto por código, ID, fonte ou índice de entrada e lista as categorias ausentes; os totais agregados continuam em `cobertura`.

O resultado mede presença de quantidade e produtividade positivas, suas unidades, fonte rastreável e dicionário mínimo completo. Não confirma que uma prancha está aprovada, que quantidade, produtividade, critério ou aceite estão tecnicamente corretos, que as unidades são compatíveis, nem que a EAP cobre 100% do escopo. `persistido: false` significa que a chamada não grava dados. A validação de IDs/pais/níveis é ferramenta separada e não substitui esta auditoria.

## Compatibilidade

- Famílias MCP 2025: handshake `initialize`.
- MCP `2026-07-28`: a validação live em 09/11/2026 falhou — `server/discover` e
  `tools/list` responderam HTTP 200 com corpo vazio no alias e no deployment direto.
  Não considerar compatibilidade moderna aprovada até um smoke completo em produção.
- Os testes independentes usam clientes oficiais **Python MCP 2.3.0**
  e **TypeScript MCP Client 2.4.0**, nos modos legado e moderno.
- Esses testes confirmam o transporte entre SDKs, **não validam as interfaces
  fechadas do Claude, do ChatGPT ou de todos os clientes disponíveis**.

## Clientes em navegador: CORS restrito

Apenas se o cliente executar MCP diretamente no navegador, configure no
ambiente do serviço:

```env
MCP_PUBLIC_ALLOWED_ORIGINS=https://app.exemplo.com,https://outro.exemplo.com
```

- Sem essa variável, requisições que incluam `Origin` não estão autorizadas.
- Somente origens HTTPS completas, explicitamente enumeradas, ou HTTP local
  (`localhost`/`127.0.0.1`) são aceitas. **Não usar `*` nem `null`.**
- A origem aprovada recebe os cabeçalhos de preflight necessários ao MCP.
- A lista deve ser atualizada apenas por quem administra o serviço.
- Clientes de servidor e desktop que não enviam `Origin` não precisam da
  configuração acima.
- **Não** liberar CORS geral nem remover a validação de Host/Origin do SDK.

## Acesso privado e dados reais de obra

- A rota `/mcp` é **diferente da rota pública** e exige
  `Authorization: Bearer <token>`, quando está configurada.
- O teste sem token deve retornar HTTP 401 quando o serviço está configurado;
  a ausência das variáveis necessárias pode produzir 503.
- Não armazenar tokens em código, logs, exemplos ou repositórios.
- Bearer estático não equivale a OAuth. Clientes que exigem OAuth 2.1 não terão
  integração privada automática sem um provedor/fluxo de autorização compatível.
- A rota privada nunca herda o CORS público. Gravações só podem ocorrer por
  ferramentas privadas autenticadas e com autorização da obra.

## Critérios antes de promover

1. Unitários e regressões pré-existentes passam.
2. Clientes MCP Python/TypeScript conectam, listam ferramentas e executam
   chamadas sintéticas em ambos os protocolos sem gravação.
3. O endpoint privado recusa chamadas anônimas, e as políticas CORS e Host
   permanecem restritas.
4. A prévia testada corresponde ao **commit exato** candidato a produção.
   Um smoke verde apontando para prévia antiga não aprova um commit novo.
5. Aprovação do PR, publicação controlada, smoke pós-publicação, rollback
   disponível caso os testes falhem.
6. Teste humano de conexão em ChatGPT/Claude, quando necessário, é critério
   separado; não afirmar sua execução com base somente nos SDKs.

## Limitações atuais

A rota pública não lê, modifica ou salva registros de obras. Arquivos Excel,
gráficos e persistência requerem recursos adicionais/privados. Os três
servidores podem ser usados separadamente: não há dependência obrigatória
de um projeto único, cliente único ou fornecedor único de IA.
