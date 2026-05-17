# ADR-0019: Superfície de Observabilidade HTTP

O servidor MCP Rust Star expunha estado interno apenas via arquivo `data/telemetry.json` (polling por arquivo). Com o transporte streamable-HTTP (ADR-0015), tornou-se viável montar endpoints REST e SSE ao lado do `/mcp` sem overhead adicional de processo.

## Contexto

Três gaps de observabilidade identificados após a Fase 5:

1. **Sem endpoint de saúde**: scripts externos e o dashboard precisavam inferir saúde lendo o arquivo de telemetria, sem saber se Ollama e PostgreSQL estavam acessíveis.
2. **Sem acesso ao ring buffer**: os 500 eventos mais recentes do EventBus (ADR-0017) existiam em memória mas não eram consultáveis de fora do processo.
3. **Sem streaming de eventos**: o dashboard actualizava via polling de arquivo a cada 10s — latência alta e ineficiente.

## Decisão

Implementar `src/services/observability.py` com `register_observability_routes(mcp, rag, bus, start_time)` usando `@mcp.custom_route(...)` do MCP SDK 1.27.1.

### Endpoints

| Endpoint | Método | Descrição |
|---|---|---|
| `/health` | GET | Status agregado: `ok`/`degraded`, uptime, Ollama, DB, ModelGuard, último evento |
| `/events/recent` | GET | Últimos N eventos do ring buffer; query params: `limit` (máx 500), `pattern` (glob) |
| `/events/stream` | GET | SSE: envia histórico dos últimos 60s ao conectar, depois stream contínuo (poll 0.5s) |
| `/metrics` | GET | Contadores agregados: tool_calls, embed_completed, rag_queries, queue_depth, uptime |

### Integração com FastMCP

`FastMCP._custom_starlette_routes` é lido em `streamable_http_app()` via `routes.extend(self._custom_starlette_routes)` — as rotas ficam no mesmo servidor uvicorn, sem porta adicional. Não requerem autenticação (design intencional para health checks e dashboards locais).

### SSE (`/events/stream`)

- Usa `EventSourceResponse` de `sse-starlette` (dependência transitiva do MCP SDK).
- Envia eventos do buffer com `ts >= agora - 60s` na conexão inicial (prevenindo flood de até 500 eventos).
- Poll a cada 0.5s no ring buffer; filtra por `ts > last_ts` para entregar apenas novos.
- Keepalive a cada 15s para manter conexão viva em proxies com timeout curto.
- Detecta desconexão via `request.is_disconnected()`.

## Alternativas consideradas

- **Push via EventBus subscription para SSE**: exigiria passar `(event_name, payload)` para handlers — quebraria API existente ou exigiria novo método `subscribe_full`. Descartado em favor do poll no ring buffer, que é igualmente eficiente dado o volume atual de eventos.
- **FastAPI montado sobre a app uvicorn**: possível, mas adiciona dependência e complexidade de montagem ASGI. `custom_route` do próprio SDK é suficiente.
- **Porta separada para observabilidade**: complica firewall, scripts e deploy. Rejeitado.

## Consequências

- `GET /health` permite health checks em < 100ms sem ler arquivo de telemetria.
- `GET /events/stream` viabiliza migração futura do dashboard de file-polling para SSE (Fase 6.5 opcional).
- `GET /metrics` oferece contadores de volume sem análise de logs.
- Nenhum impacto no transporte MCP em `/mcp` — rotas são totalmente independentes.
- `_SERVER_START_TIME = time.time()` registrado no topo de `main.py` antes do `RAGService()` para uptime preciso.

---

## Fase 6.5 — Avaliação: migrar dashboard de file-watching para `/events/stream`

**Conclusão: manter watchfiles. Migração não recomendada para o dashboard local.**

### Situação atual do dashboard

`dashboard/fetcher.py` usa `watchfiles.watch()` — event-driven no filesystem. O SO notifica o processo quando `data/dashboard_state.json` muda; não há polling por intervalo fixo. Latência efetiva é < 250ms (throttle do `TelemetryWriter`). Fallback para poll de 2s apenas quando `watchfiles` falha.

### Por que `/events/stream` não melhora o dashboard local

| Dimensão | watchfiles + snapshot | `/events/stream` SSE |
|---|---|---|
| Latência | < 250ms (throttle TelemetryWriter) | ≤ 500ms (poll do endpoint SSE) |
| Dados por entrega | Snapshot completo (indexing, batch, inventory, log_tail, recent_events) | Evento individual — requer state reconstruction |
| Complexidade no cliente | Lê JSON e mapeia campos | Reescrever lógica de estado acumulativo + reconexão SSE |
| Modo STDIO legado | Funciona (sem HTTP) | Falha — endpoint não existe sem streamable-HTTP |
| Deployment remoto | Requer filesystem compartilhado | Funciona via rede |

### Quando migrar faz sentido

`/events/stream` vale para clientes **remotos** (dashboard em outra máquina, CI, monitoramento externo) onde não há acesso ao filesystem do servidor. Para o dashboard TUI local que já lê o arquivo com watchfiles, a migração aumentaria complexidade sem ganho mensurável.

### Decisão

Manter arquitetura atual. `/events/stream` permanece disponível para uso externo. Se um dashboard web remoto for desenvolvido no futuro, deve consumir SSE diretamente em vez de montar o filesystem.
