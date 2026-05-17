Plano: Estabilização MCP Rust Star v2.0
Princípios de design
Princípio	Razão
Single-flight em modelos locais	Você confirmou: 1 modelo = VRAM toda; serialização é OK
Event-driven internamente	Telemetria reage a eventos, não pesquisa estado
HTTP como transporte único	Multi-cliente (IDE + CLI) sem duplicação de processo
Zero novas dependências externas	EventBus, ModelGuard são in-process Python puro
Vertical slicing	Cada fase entrega valor sozinha, com testes próprios
ADRs a criar
ADR	Decisão
ADR-0015	Migração para streamable-http (substitui STDIO)
ADR-0016	ModelGuard: serialização global de operações que tocam Ollama
ADR-0017	EventBus in-process como espinha dorsal de observabilidade
ADR-0018	Lifecycle: graceful shutdown + health probes
Fase 1 — Transporte HTTP
Entrega: servidor responde via http://127.0.0.1:PORT/mcp em vez de stdin/stdout.

Mudanças:

data/defaults.json: nova seção "server": { "transport": "streamable-http", "host": "127.0.0.1", "port": 8765 }
src/main.py:1333: mcp.run() → mcp.run(transport=cfg["transport"], host=cfg["host"], port=cfg["port"])
Remover _windows_stdin_keepalive (não faz mais sentido sem stdin)
Atualizar Regra 01 (.agents/rules/): "stdout sacro para JSON-RPC" passa a valer só em modo STDIO legado; em HTTP, logger pode ir para stdout também
Script de inicialização: scripts/start_server.bat (ou .ps1) que sobe o servidor em background
Snippet de config IDE no docs/SESSION_LOG.md:

{ "mcpServers": { "mcp-rust-star": { "url": "http://127.0.0.1:8765/mcp" } } }
Teste: conectar IDE + CLI Python simples (mcp.client.streamable_http) na mesma sessão, confirmar que ambos veem o mesmo list_projects.

Risco: baixo. Isolado de tudo o que vem depois.

Fase 2 — ModelGuard (fila única para modelos locais)
Entrega: qualquer ferramenta que toque Ollama passa por um único asyncio.Lock global. Chamadas concorrentes ficam em fila FIFO observável.

Estrutura proposta — src/services/model_guard.py:


ModelGuard
  - lock: asyncio.Lock
  - current_holder: { tool_name, started_at, kind: "embed"|"chat"|"vision" }
  - queue: list of { tool_name, enqueued_at }
  - async acquire(tool_name, kind) → context manager
  - stats() → { holder, queue_depth, total_acquires }
Decorator:


@with_model_guard(kind="embed")
async def index_directory(...): ...
Aplicar em: index_file, index_directory, batch_index_projects (envolve o worker, não cada arquivo), ask_knowledge_base, analyze_screenshot, index_image, retry_failed_files.

Eventos emitidos (fase 3 consome):

model.queued { tool, kind, depth_at_enqueue }
model.acquired { tool, kind, waited_ms }
model.released { tool, kind, held_ms }
Sutileza importante: batch_index_projects segura o lock durante o batch inteiro? Ou libera entre arquivos? Recomendo segurar durante batch inteiro — soltar entre arquivos abriria janela para ask_knowledge_base se intercalar e quebrar o VRAM Eject Pattern. Você aceitou a latência: melhor consistência.

Teste: spawn 5 tarefas concorrentes de ask_knowledge_base + 1 batch_index → confirmar serialização e que stats() mostra fila correta.

Fase 3 — EventBus (as "bandeiras")
Entrega: ponto central de pub/sub. Substitui as chamadas espalhadas _publish_telemetry() em src/main.py.

Estrutura — src/services/event_bus.py:


EventBus (singleton)
  - subscribe(event_pattern, handler)   # "embed.*" funciona com wildcard
  - unsubscribe(token)
  - emit(event_name, payload)           # sync, dispara handlers em background
  - emit_async(event_name, payload)     # await até todos handlers
  - history(event_pattern, limit=100)   # ring buffer para debug
Catálogo inicial de eventos:

Namespace	Eventos
server	starting, started, stopping, stopped, health.tick
tool	invoked, completed, failed (todas as @mcp_tool)
model	queued, acquired, released, loaded, unloaded
embed	batch.started, project.started, file.processed, project.completed, batch.completed, cancelled
rag	query.received, query.answered, query.failed
vision	started, completed
index	source.added, source.removed
Garantias:

Async-safe (handlers rodam via asyncio.create_task para não bloquear o emissor)
Erro num handler não derruba os outros (try/except com logger.error, nunca except: pass — respeita Zero Panic)
Ring buffer interno de 500 eventos para /debug/events consultar
Zero dependência externa
Wire-up: o mcp_tool_with_logging em src/main.py:132 passa a emitir tool.invoked/completed/failed automaticamente. Demais eventos são emitidos em pontos cirúrgicos do código existente.

Fase 4 — Telemetria via assinatura de eventos
Entrega: TelemetryWriter deixa de ser empurrado por callbacks espalhados; ele assina eventos do bus e mantém estado próprio.

Mudanças em src/services/telemetry_writer.py:

Recebe EventBus no construtor
No __init__, registra handlers para embed.*, rag.*, model.*, tool.*, server.*
Cada handler atualiza um campo do snapshot em memória e dispara o write throttled
Heartbeat thread continua existindo (escreve a cada 10s mesmo sem evento, para o dashboard saber que o servidor está vivo)
Bonus: o dashboard_state.json ganha campo novo recent_events: [...] com últimos 20 eventos do bus — o dashboard pode mostrar uma "linha do tempo" do que está acontecendo, sem precisar consultar logs.

ADR-0014 (dashboard event-driven standby) finalmente faz jus ao nome.

Fase 5 — Lifecycle robusto
Entrega: servidor sobe e desce de forma previsível.

Mudanças:

Startup probe (antes de mcp.run):
Ollama reachable em rag.ollama.base_url?
PostgreSQL reachable?
Porta 8765 livre?
Se algo falhar, fail-fast com mensagem amigável no stderr, exit code != 0
Emite server.starting → checks → server.started
Signal handlers SIGTERM/SIGINT:
Emite server.stopping
Cancela _embed_task se houver
Aguarda ModelGuard drenar (timeout 5s, depois força)
_telemetry.flush() síncrono
rag.ollama.unload_models()
Emite server.stopped
Remove data/server.pid
PID file diagnóstico (não takeover, só registro): data/server.pid escrito no startup, removido no shutdown limpo. Útil para scripts/stop_server.bat mandar SIGTERM.
Fase 6 — Superfície de observabilidade (HTTP nativo)
Entrega: endpoints HTTP auxiliares ao lado do MCP, na mesma porta.

Endpoint	Função
GET /health	JSON com { status, uptime, ollama, db, model_guard, last_event_at }
GET /events/recent?limit=100	Histórico do ring buffer do EventBus
GET /events/stream (SSE)	Stream ao vivo dos eventos — dashboard pode consumir em vez de polling no JSON
GET /metrics	Contadores: total tools invocados, fila depth média, embed throughput
Esses endpoints podem subir como app Starlette/FastAPI montado paralelo ao MCP — FastMCP expõe a app ASGI interna, dá para adicionar rotas. Detalhe técnico a confirmar na implementação.

O dashboard pode opcionalmente migrar de file-polling para /events/stream. Mas só fazemos isso se a fase 4 deixar dor — não é pré-requisito.

Não-escopo (decidido fora)
❌ Autenticação / TLS (single-user localhost — 127.0.0.1 é suficiente)
❌ Multi-tenancy / RBAC
❌ Distributed tracing, Prometheus, OpenTelemetry
❌ Docker (você dispensou)
❌ Hot-reload de transport/porta sem restart
Ordem de execução e estimativa de risco
#	Fase	Esforço	Risco	Reversível?
1	Transporte HTTP	1 sessão	Baixo	Sim (config flag)
2	ModelGuard	1-2 sessões	Médio (toca todas as @tools)	Sim (decorator opt-out)
3	EventBus	1 sessão	Baixo (aditivo)	Sim
4	Telemetria via bus	1 sessão	Médio (substitui mecanismo atual)	Sim (writer dual durante transição)
5	Lifecycle	1 sessão	Baixo	Sim
6	Endpoints obs	1 sessão	Baixo	Sim (rotas opcionais)
Cada fase termina com: ADR escrito, testes verdes, docs/SESSION_LOG.md atualizado.

Como começar
Recomendo começar pela Fase 3 (EventBus) antes da 1 (HTTP). Razão: o EventBus é a espinha dorsal — se ele entra primeiro, podemos integrar a fila e a telemetria sobre ele imediatamente, e a migração HTTP fica como troca cirúrgica de uma linha. Inverter a ordem faz a Fase 1 ter telemetria velha e depois ter que reescrever na Fase 4.

Ordem revisada que recomendo: 3 → 2 → 4 → 1 → 5 → 6.

Quer que eu comece escrevendo o ADR-0017 (EventBus) + esqueleto de src/services/event_bus.py com testes? Ou prefere primeiro discutirmos a ordem invertida que sugeri?