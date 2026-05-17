## Tasks — Plano de Estabilização MCP Rust Star v2.0
Ordem de execução: 3 → 2 → 4 → 1 → 5 → 6

---

### ✅ Fase 3 — EventBus In-Process (CONCLUÍDA)

- [x] Fase 3.1 — Ler .agents/rules/04-vertical-slicing-and-adrs e .agents/skills/grill-with-docs/ADR-FORMAT.md para alinhar formato do ADR-0017
- [x] Fase 3.2 — Escrever docs/adr/0017-event-bus-in-process.md (contexto, decisão, alternativas, consequências, catálogo de eventos)
- [x] Fase 3.3 — Aplicar skill tdd: escrever tests/services/test_event_bus.py cobrindo subscribe, emit sync/async, wildcards, ring buffer, isolamento de erros
- [x] Fase 3.4 — Implementar src/services/event_bus.py (singleton, subscribe/unsubscribe, emit/emit_async, history ring buffer 500, asyncio.create_task seguro)
- [x] Fase 3.5 — Wire-up: integrar EventBus em mcp_tool_with_logging (src/main.py:132) para emitir tool.invoked/completed/failed automaticamente
- [x] Fase 3.6 — Rodar suíte de testes, atualizar docs/SESSION_LOG.md com fechamento da Fase 3

---

### ✅ Fase 2 — ModelGuard (CONCLUÍDA)

- [x] Fase 2.1 — Escrever docs/adr/0016-model-guard-serializacao-ollama.md (justifica lock global, decisão de segurar lock durante batch inteiro)
- [x] Fase 2.2 — TDD: tests/services/test_model_guard.py (lock FIFO, stats(), eventos model.queued/acquired/released, 5 concorrentes + 1 batch)
- [x] Fase 2.3 — Implementar src/services/model_guard.py com asyncio.Lock global, holder/queue observáveis, integração com EventBus
- [x] Fase 2.4 — Criar decorator @with_model_guard(kind=...) e aplicar em index_file, index_directory, batch_index_projects, ask_knowledge_base, analyze_screenshot, index_image, retry_failed_files
- [x] Fase 2.5 — Validar VRAM Eject Pattern com lock segurando batch inteiro; rodar testes; atualizar SESSION_LOG

---

### ✅ Fase 4 — Telemetria via assinatura de eventos (CONCLUÍDA)

- [x] Fase 4.1 — Refatorar src/services/telemetry_writer.py: receber EventBus no construtor, registrar handlers para embed.*, rag.*, model.*, tool.*, server.*
- [x] Fase 4.2 — Adicionar campo recent_events (últimos 20) ao dashboard_state.json; manter heartbeat thread escrevendo a cada 10s
- [x] Fase 4.3 — Remover chamadas espalhadas de _publish_telemetry em src/main.py, substituindo por bus.emit em pontos cirúrgicos (mantendo writer dual durante transição)
- [x] Fase 4.4 — Atualizar tests/dashboard/ para validar pipeline orientado a eventos; honrar ADR-0014; atualizar SESSION_LOG

---

### ✅ Fase 1 — Transporte HTTP (CONCLUÍDA)

- [x] Fase 1.1 — Escrever docs/adr/0015-transporte-streamable-http.md (motivação multi-cliente, contraste com STDIO, escopo de Regra 01)
- [x] Fase 1.2 — Adicionar seção server (transport/host/port) em data/defaults.json; trocar mcp.run() em src/main.py para streamable-http
- [x] Fase 1.3 — Remover _windows_stdin_keepalive; atualizar .agents/rules/01 deixando 'stdout sacro' válido só no modo STDIO legado
- [x] Fase 1.4 — Criar scripts/start_server.bat e .ps1; adicionar snippet de config IDE no docs/SESSION_LOG.md
- [ ] Fase 1.5 — Testar IDE + cliente Python mcp.client.streamable_http simultâneos vendo o mesmo list_projects; atualizar SESSION_LOG

---

### ✅ Fase 5 — Lifecycle robusto (CONCLUÍDA)

- [x] Fase 5.1 — Escrever docs/adr/0018-lifecycle-graceful-shutdown.md (probes, signal handlers, PID file diagnóstico)
- [x] Fase 5.2 — Implementar startup probes (Ollama, PostgreSQL, porta livre) com fail-fast e emissão server.starting/started
- [x] Fase 5.3 — Implementar signal handlers SIGTERM/SIGINT: drena ModelGuard (timeout 5s), flush telemetria, unload modelos, emite server.stopped
- [x] Fase 5.4 — Adicionar data/server.pid (escrita no startup, remoção no shutdown limpo); criar scripts/stop_server.bat
- [x] Fase 5.5 — 13 testes unitários em tests/services/test_lifecycle.py; todos passando (69 total na suite)

---

### ✅ Fase 6 — Superfície de observabilidade HTTP (CONCLUÍDA)

- [x] Fase 6.1 — Investigar como FastMCP expõe a app ASGI interna: `@mcp.custom_route(...)` via `_custom_starlette_routes` (MCP SDK 1.27.1)
- [x] Fase 6.2 — Implementar GET /health (status, uptime, ollama, db, model_guard, last_event_at)
- [x] Fase 6.3 — Implementar GET /events/recent (limit/pattern) e GET /events/stream (SSE, poll 0.5s, histórico 60s)
- [x] Fase 6.4 — Implementar GET /metrics (tool_calls, embed_completed, rag_queries, queue_depth, uptime)
- [x] Fase 6.5 — (Opcional) avaliar migração do dashboard de file-polling para /events/stream; documentar trade-off — watchfiles já é event-driven (< 250ms); SSE não melhora dashboard local; decisão registrada em ADR-0019 §Fase 6.5
