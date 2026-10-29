# Deploy Vercel (preview/produção)

Esta integração **não substitui o deploy do Render**. As ferramentas e algoritmos
continuam no Python; apenas o transporte é adaptado para chamadas HTTP sem sessão.

## Ambiente obrigatório (Vercel > Project > Settings > Environment Variables)

- `MCP_API_TOKEN`: segredo longo e aleatório. O Claude deve enviar
  `Authorization: Bearer <seu-token>` no conector HTTP. Nunca versionar.
- `TURSO_URL`: URL do banco Turso/libSQL persistente exclusivo deste MCP.
- `TURSO_TOKEN`: token Turso deste banco. **Sem esses dois, o servidor retorna 503**.
- `MCP_REQUIRE_TURSO=1`: garante que o health check responda 503 quando não configurado.

Defina as variáveis em produção **e** preview conforme necessidade; faça um novo
deploy após alterar as variáveis. Não use SQLite local para dados persistentes
na Vercel (sistema de arquivos efêmero).

## Rotas

- `POST https://<project>.vercel.app/mcp`: MCP Streamable HTTP stateless
- `GET https://<project>.vercel.app/healthz`: apenas prontidão (sem segredos)
- Todos os métodos em `/mcp` exigem token; sem token -> 401.
- Sem configuração mínima -> 503, sem carregar ferramentas nem bancos.

## Testes obrigatórios antes de declarar aprovação

1. `GET /healthz` retorna 200 apenas quando configurado.
2. `POST /mcp` sem Authorization retorna 401.
3. `tools/list` com Authorization lista ferramentas do MCP original.
4. `tools/call` de uma ferramenta **somente leitura** funciona.
5. Após um novo deploy, dados persistem no Turso (para EAP/Cronograma).
6. Uma alteração via MCP só ocorre em projeto de teste (não em obra real).

A função de entrada está em `api/index.py`, a URL externa é `/mcp`.
O token simples por header é apropriado para conexões privadas configuradas
manualmente; publicação pública multiusuário requer OAuth/autorização por usuário.
