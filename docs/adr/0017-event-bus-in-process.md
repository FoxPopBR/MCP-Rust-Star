# ADR-0017: EventBus In-Process como Espinha Dorsal de Observabilidade

O servidor emite eventos de ciclo de vida (tool invocada, embed iniciado, modelo adquirido, etc.) a partir de vários pontos do código, e os consumidores desses eventos (TelemetryWriter, dashboard, futuro /events/stream) estavam acoplados diretamente aos emissores via callbacks espalhados (`_publish_telemetry`, `_on_state_change`). Decidimos introduzir um EventBus in-process singleton como ponto único de pub/sub, substituindo todos os callbacks por assinaturas declarativas.

## Contexto

O padrão atual tem três problemas:
1. **Acoplamento direto**: `rag._on_state_change = _publish_telemetry` liga RAGService ao TelemetryWriter por atribuição de atributo — qualquer novo consumidor exige editar o código do emissor.
2. **Dispersão**: chamadas manuais de `_publish_telemetry()` em `_embed_log`, `_walk_and_index_sync` e `_batch_embed_worker` significam que adicionar um novo evento requer encontrar e editar múltiplos pontos.
3. **Sem histórico observável**: não há como consultar "o que aconteceu nos últimos 5 minutos" sem ler logs — prejudica diagnóstico e o endpoint `/events/recent` planejado (Fase 6).

## Decisão

Implementar `src/services/event_bus.py` com as seguintes garantias:

- **Singleton** acessível via `get_event_bus()` — sem estado global explícito, sem imports circulares.
- **Wildcard subscriptions**: `subscribe("embed.*")` captura `embed.file.processed`, `embed.batch.completed`, etc.
- **Async-safe**: `emit()` é síncrono e dispara handlers em `asyncio.create_task` para não bloquear o emissor; `emit_async()` aguarda todos os handlers (usado em shutdown).
- **Isolamento de erros**: erro num handler é logado via `logger.error()` e não cancela os demais — respeita Regra 00 (Zero Panic).
- **Ring buffer**: 500 eventos em memória, consultável via `history(pattern, limit)` — alimenta o endpoint `/events/recent` e diagnóstico em tempo real.
- **Zero dependência externa**: Python puro, `asyncio` nativo.

## Catálogo inicial de eventos

| Namespace | Eventos |
|-----------|---------|
| `server`  | `starting`, `started`, `stopping`, `stopped`, `health.tick` |
| `tool`    | `invoked`, `completed`, `failed` |
| `model`   | `queued`, `acquired`, `released`, `loaded`, `unloaded` |
| `embed`   | `batch.started`, `project.started`, `file.processed`, `project.completed`, `batch.completed`, `cancelled` |
| `rag`     | `query.received`, `query.answered`, `query.failed` |
| `vision`  | `started`, `completed` |
| `index`   | `source.added`, `source.removed` |

## Alternativas consideradas

- **asyncio.Queue entre tasks**: bom para pipelines 1:1, mas não suporta múltiplos consumidores independentes (fan-out) sem replicação manual de filas.
- **Biblioteca externa (blinker, PyDispatcher)**: adiciona dependência sem ganho funcional — o caso de uso é simples o suficiente para Python puro.
- **Manter callbacks diretos**: não escala — cada novo consumidor (dashboard SSE, ModelGuard stats) exige editar emissores.

## Consequências

- `TelemetryWriter` (Fase 4) deixa de ser chamado diretamente; assina `embed.*`, `rag.*`, `model.*`, `tool.*`, `server.*`.
- `mcp_tool_with_logging` passa a emitir `tool.invoked` / `tool.completed` / `tool.failed` automaticamente, sem alterar as tools individualmente.
- O endpoint `/events/recent` (Fase 6) é trivial: retorna `event_bus.history(limit=N)`.
- Handlers lentos não bloqueiam o servidor (isolados em tasks); handlers com bugs não derrubam outros (isolamento de exceção).
- Ring buffer de 500 eventos consome ~500 KB de RAM no pior caso — negligenciável.
