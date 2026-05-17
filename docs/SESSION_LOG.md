# Diário de Sessão: MCP Rust Star Knowledge Server

Este documento é o registro mestre de transição entre sessões. Ele detalha o estado atual do projeto, marcos alcançados e o planejamento imediato para a continuidade do desenvolvimento.


---

## 🗓️ Sessão: 16/05/2026 (Parte 5) — Fase 4: Telemetria via EventBus (ADR-0014)

### Contexto
Continuação do Plano de Estabilização v2.0. Fase 4 completa: TelemetryWriter orientado a eventos, remoção de `_publish_telemetry`, wire-up de `bus.emit` e 10 novos testes.

Uma IA rogue reverteu o `src/main.py` via `git checkout --` durante a sessão anterior, apagando todas as mudanças das Fases 3, 2 e 4. A sessão foi dedicada a diagnosticar o dano e reaplicar todas as alterações.

### Conquistas
- **`src/services/telemetry_writer.py`** — Refatorado para aceitar `bus` + 4 lambdas de estado no construtor. Assina `embed.*`, `rag.*`, `model.*`, `tool.*`, `server.*`. Inclui `recent_events` (últimos 20) no snapshot. `heartbeat_loop` recebe um único argumento `stop_event`.
- **`src/main.py`** — `_publish_telemetry()` removido inteiramente (0 ocorrências). Substituído por 5 chamadas cirúrgicas de `_bus.emit()` nos pontos relevantes. `_telemetry` inicializado com `bus=_bus` e as 4 lambdas de estado. Heartbeat thread corrigida para `args=(_heartbeat_stop,)`.
- **`tests/dashboard/test_telemetry_event_driven.py`** — Novo arquivo com 10 testes TDD validando: assinatura automática (4 eventos distintos), writer sem bus, `recent_events` no snapshot, limite de 20 eventos, heartbeat thread, JSON atômico válido e schema v2.
- **Wire-up mantido intacto**: `@with_model_guard` em 7 locais, `mcp_tool_with_logging` emitindo `tool.invoked/completed/failed`, `rag._on_state_change` via `bus.emit`.

### Arquivos alterados
| Arquivo | Mudança |
|---|---|
| `src/services/telemetry_writer.py` | Refatorado — bus + lambdas, recent_events, heartbeat single-arg |
| `src/main.py` | `_publish_telemetry` removido; 5x `_bus.emit`; telemetry dual-mode |
| `tests/dashboard/test_telemetry_event_driven.py` | Novo — 10 testes TDD |
| `docs/operation/tasks-Plano_Estabilização.md` | Fase 4 marcada como concluída |

### Resultado dos testes
**55/55 testes passando** (10 event-driven + 14 EventBus + 10 ModelGuard + 3 live_repaints + 18 state_decider).

### Próximo passo
**Fase 1 — Transporte HTTP**: ADR-0015, streamable-http transport, `data/defaults.json` com seção server, remoção de `_windows_stdin_keepalive`, scripts de start.

---

## 🗓️ Sessão: 16/05/2026 (Parte 4) — Fase 2: ModelGuard (ADR-0016)

### Contexto
Continuação do Plano de Estabilização v2.0. Fase 2 completa: ADR + testes TDD + implementação + wire-up nas tools.

### Conquistas
- **ADR-0016** (`docs/adr/0016-model-guard-serializacao-ollama.md`) — documentado; decisão crítica de segurar o lock durante o batch inteiro.
- **`src/services/model_guard.py`** — implementado: `asyncio.Lock` FIFO, `stats()`, eventos `model.queued/acquired/released`, decorator `@with_model_guard`, singleton `get_model_guard()`.
- **`tests/services/test_model_guard.py`** — 10 testes TDD cobrindo: acquire/release básico, serialização de 2 e 5 tasks concorrentes, queue_depth, total_acquires, eventos model.*, decorator, singleton.
- **Wire-up em `src/main.py`** — decorator aplicado em 7 tools Ollama e em `_batch_embed_worker` (segura lock durante batch inteiro):
  - `kind="embed"`: `index_file`, `index_directory`, `retry_failed_files`, `_batch_embed_worker`
  - `kind="vision"`: `index_image`, `analyze_screenshot`
  - `kind="chat"`: `ask_knowledge_base`

### Arquivos alterados
| Arquivo | Mudança |
|---|---|
| `src/services/model_guard.py` | Novo — implementação completa |
| `tests/services/test_model_guard.py` | Novo — 10 testes TDD |
| `docs/adr/0016-model-guard-serializacao-ollama.md` | Novo — ADR da decisão |
| `src/main.py` | Import `with_model_guard, get_model_guard`; 8 pontos de wire-up |

### Resultado dos testes
24/24 testes passando (`tests/services/` — 14 EventBus + 10 ModelGuard).

### Próximo passo
**Fase 4 — TelemetryWriter orientado a eventos**: refatorar `src/services/telemetry_writer.py` para assinar o EventBus em vez de ser chamado diretamente.

---

## 🗓️ Sessão: 16/05/2026 (Parte 3) — Fase 3: EventBus In-Process (ADR-0017)

### Contexto
Início da execução do Plano de Estabilização v2.0 (`docs/operation/2026-05-16Plano Estabilização MCP Rust Star v2.0.md`). Ordem de execução: **3 → 2 → 4 → 1 → 5 → 6**.

### Conquistas
- **ADR-0017** (`docs/adr/0017-event-bus-in-process.md`) escrito — justifica pub/sub in-process, cataloga todos os namespaces de eventos, descarta alternativas (asyncio.Queue fan-out, blinker).
- **`src/services/event_bus.py`** implementado: singleton `get_event_bus()`, `subscribe`/`unsubscribe`, `emit` (síncrono, handlers async via `create_task`), `emit_async` (aguarda todos), wildcards via `fnmatch`, ring buffer 500 eventos, isolamento de erros por handler.
- **`tests/services/test_event_bus.py`** — 14 testes verdes cobrindo todos os contratos públicos: subscribe, emit básico, wildcards, unsubscribe, isolamento de exceção, ring buffer (order, limit, filter, overflow), emit_async, singleton.
- **Wire-up em `src/main.py`** — decorator `mcp_tool_with_logging` emite agora automaticamente `tool.invoked`, `tool.completed` e `tool.failed` para todas as tools MCP, sem alterar nenhuma tool individualmente.

### Arquivos alterados
| Arquivo | Mudança |
|---|---|
| `src/services/event_bus.py` | Novo — implementação completa do EventBus |
| `tests/services/__init__.py` | Novo — pacote de testes de serviços |
| `tests/services/test_event_bus.py` | Novo — 14 testes TDD |
| `docs/adr/0017-event-bus-in-process.md` | Novo — ADR da decisão |
| `src/main.py` | Import de `get_event_bus`; 3 emissões de eventos no decorator |

### Próximo passo
**Fase 2 — ModelGuard**: ADR-0016 + `src/services/model_guard.py` + decorator `@with_model_guard`.

---

## 🗓️ Sessão: 16/05/2026 (Parte 2) - Dashboard Standby + Event-Driven (ADR-0014)

### 1. Principais Conquistas e Fatos

- **Migração para Arquitetura Event-Driven**: O dashboard deixou de usar polling (250ms) e passou a ser orientado a eventos via `watchfiles`. O `DataFetcher` agora bloqueia aguardando mudanças no `dashboard_state.json`, reduzindo drasticamente o overhead de I/O em ociosidade.
- **Sistema de Refcount de Atividade**: Implementado no `TelemetryWriter` um sistema de contagem de referência para atividade. Ferramentas MCP e workers de background agora sinalizam quando estão ativos, permitindo ao dashboard entrar em modo **Standby** visual.
- **Visual Status LED (🟢/🟡/🔴/⚫)**: O Header do dashboard agora exibe um LED de status dinâmico e labels de estado baseados na lógica do `decide_state.py` (determinação de Ativo, Standby, Erro ou Offline).
- **Heartbeat do Servidor (10s)**: Thread dedicada no servidor realiza um "touch" na telemetria a cada 10 segundos, permitindo ao dashboard detectar se o servidor caiu (Status ⚫ Offline) sem polling agressivo.
- **Spinner Condicional**: O spinner de atividade agora é exibido apenas quando o servidor está em estado `active`. Em standby, o spinner congela em um ponto estático (`·`), melhorando a legibilidade do sistema.
- **Regression Testing**: Criado `tests/dashboard/test_state_decider.py` para validar as transições de estado visual (offline/stale/active/standby).

### 2. Mudanças Técnicas
- **`src/services/telemetry_writer.py`**: Adicionado `activity()` context manager, `heartbeat_loop` e `activity` no snapshot (Schema v2).
- **`src/main.py`**: Ferramentas MCP e worker injetados com rastreamento de atividade; thread de heartbeat iniciada no entry point.
- **`dashboard/fetcher.py`**: Refatorado de polling para `watchfiles`.
- **`dashboard/app.py`**: UI atualizada para refletir os novos estados visuais e lógica de standby.
- **`dashboard/state_decider.py`**: Nova lógica centralizada de decisão de estado.

### 3. Consequências
- **Zero-Polling Dashboard**: O sistema agora é 100% orientado a eventos para telemetria de disco.
- **Resiliência**: Detecção de crash via heartbeat timeout (30s) implementada.
- **Eficiência**: Próximo de 0% de uso de CPU/IO pelo dashboard em modo standby.

---

## 🗓️ Sessão: 16/05/2026 - Pipeline de Telemetria Unificada + Fix do Live Freeze

### 1. Principais Conquistas e Fatos

- **Diagnóstico do "Live Freeze" do Dashboard (skill `diagnose`)**: Harness descartável `tools/diag_live_freeze.py` reproduziu o bug em isolamento (~2s, pass/fail determinístico). Hipótese **H1 confirmada**: `rich.live.Live` com `auto_refresh=False` e sem `live.refresh()` mantém o frame inicial congelado para sempre. Demais hipóteses (KeyError, lock contention, OS scheduling) falsificadas. Detalhes em [ADR-0012](adr/0012-dashboard-live-freeze-postmortem.md).

- **Fix aplicado em `dashboard/app.py:594`**: trocado para `auto_refresh=True, refresh_per_second=25` + `stop_event.wait(0.25)` no loop. Rich passa a fazer repaint autônomo via thread daemon `_RefreshThread`, mesmo se o `DataFetcher` travar.

- **Pipeline de Telemetria Unificado ([ADR-0013](adr/0013-dashboard-state-unified.md))**: criado `src/services/telemetry_writer.py` com `TelemetryWriter` (writer único, throttle 250ms, escrita atômica) e `InventoryProvider` (cache TTL 60s sobre `db.list_sources()`). Agora **um único arquivo** `data/dashboard_state.json` substitui o tripé legado (`current_indexing.json` + `embed_batch.json` + tail físico de `mcp_error.log`).

- **Wire-up em `src/main.py`**: closure `_publish_telemetry` plugada em `rag._on_state_change`, em `_embed_log`, em `_walk_and_index_sync`, em `_batch_embed_worker` (com `flush()` no `finally`) e após cada `search_knowledge` (popula `last_query`).

- **`dashboard/fetcher.py` reescrito**: assinatura simplificada `(ollama_url, state_file)`. Lê apenas `dashboard_state.json` e sintetiza `state_view` + `batch_view` para preservar a API dos painéis existentes sem editá-los um a um. Painel `FILA DE PROJETOS` voltou a funcionar.

- **Regression test criado**: `tests/dashboard/test_live_repaints.py` (3 testes: `test_auto_refresh_true_repaints`, `test_manual_refresh_repaints`, `test_no_refresh_freezes`). CI trava se alguém reintroduzir `auto_refresh=False` sem refresh manual.

- **Limpeza de legado**: removidos `dashboard.py` (raiz), `tools/diag_live_freeze.py` (promovido a teste), `data/current_indexing.json` e `data/embed_batch.json` (substituídos pelo snapshot unificado).

### 2. Princípio reforçado

> **Dashboard jamais lê fisicamente `logs/mcp_error.log`.** O tail (28 linhas) agora vem dentro do snapshot unificado (`dashboard_state.json::log_tail`), capturado em memória pelo handler de `_embed_log`. Elimina contenção de file lock — causa documentada de dois freezes anteriores.

### 3. Validação em Produção

**Smoke test runtime confirmado em 16/05/2026**: servidor + dashboard rodando pareados; `data/dashboard_state.json` gerado corretamente; painéis (incluindo `FILA DE PROJETOS`) renderizam sem freeze. Pipeline unificado em produção.

### 4. Próximos Passos Sugeridos

1. **Modo Standby / Event-Driven** (proposto pelo usuário em 16/05/2026): substituir polling contínuo do dashboard por arquitetura idle/active baseada em sinal de atividade do servidor. Detalhes em discussão — provável fonte de uma ADR-0014.
2. **Validação de schema** do `dashboard_state.json` contra um esquema fixo (próximo regression test natural).
3. Análise dedicada de eficiência do dashboard (pendência herdada — agora viável com o pipeline estabilizado).

---

## 🗓️ Sessão: 15/05/2026 - Estabilização e Elite Pipeline

### 1. Principais Conquistas e Fatos
- **Estabilização Crítica do RAG**: Resolvemos os travamentos de VRAM e timeouts do Ollama implementando a **Subdivisão Recursiva** de fragmentos. Agora, se um arquivo falha por ser muito grande, o sistema o divide automaticamente até que o embedding seja possível.
- **Dashboard de Engenharia (Real-Time)**: Substituímos os mocks por um painel real construído com `rich`. O dashboard agora reflete fielmente o estado do `RAGService` (Novos, Cache, Ignorados) e exibe logs coloridos via `stderr`.
- **Início do "Heavy Test" (FoxOT)**: Iniciamos a indexação massiva de 11.000+ arquivos. Em apenas 15 minutos, processamos mais de 1.500 novos arquivos com 0 erros, validando a robustez do motor.
- **Institucionalização Técnica**: Criamos o `docs/ARCHITECTURE.md` (detalhando o sistema em 4 etapas) e o `docs/SUGGESTIONS.md` (backlog de inovações).

### 📔 Diário de Transição de Sessão - MCP Rust Star

- **Última Atualização**: 15/05/2026 16:00
- **Status do Motor**: Indexação de `FoxOT` em andamento (~2.6k+ arquivos).

---

## 1. Estado da Infraestrutura (PostgreSQL)
A migração para persistência industrial foi concluída. O banco de dados agora possui:
- **Tabela `knowledge_foxot`**: Ativa, com índice vetorial pgvector operando em 4096 dimensões (qwen3-embedding).
- **Isolamento**: Verificado. Consultas ao `project_id="Rust Star"` não acessam os fragmentos do `FoxOT`.
- **Integridade**: O `RAGService` está utilizando o padrão de batching para evitar sobrecarga de conexão.

## 2. Telemetria e Monitoramento
- **Dashboard (`dashboard.py`)**: Operacional via `dashboard.bat`. Lê o estado compartilhado de `data/current_indexing.json`.
- **Progresso FoxOT**: Atualmente processando a subpasta `canary-engine\data-otservbr-global\npc`. 
- **Logs de Erro**: O arquivo `logs/mcp_error.log` está limpo (0 erros nas últimas 1.000 iterações).

## 3. Auditoria de Regras e Governança
- **Regra 00**: Atualizada com o protocolo de "Stop & Think" e Diário de Sessão mandatório.
- **Regra 05**: Nova regra criada para formalizar o **Enriquecimento de Metadados** (Categorização por Path).
- **ADR-0005 e 0006**: Criados para documentar a troca de DB e a arquitetura de monitoramento.

## 4. O que falta (Próxima Sessão)
1.  **Validação do FoxOT**: Assim que a indexação NPC terminar, realizar uma pergunta complexa de Lua para testar a precisão do RAG no Postgres.
2.  **Enriquecimento de Metadados**: Implementar o injetor de `category` no `vector_store_postgres.py` baseado nos diretórios (`monster`, `npc`, `spell`).
3.  **Otimização de Busca**: Ajustar o Top-K para 7 em consultas de lore e 3 em consultas de código.

---
**Nota para o Próximo Agente**: Não confie na sua "eficiência natural". Re-leia as regras da `GEMINI.md` sobre superficialidade. Verifique se o Postgres ainda está de pé (`check_ollama_status`) antes de qualquer pergunta.

### 2. Desafios Superados
- **Caminhos Absolutos**: Corrigimos a "falha de visão" do dashboard garantindo que tanto o servidor MCP quanto o script de monitoramento usem caminhos absolutos baseados no root do projeto para acessar os arquivos de estado (`current_indexing.json`).
- **Gestão Proativa de VRAM**: Implementamos a ejeção forçada de modelos do Ollama entre grandes blocos de tarefas, garantindo que a GPU do usuário permaneça livre para outras atividades.

### 3. Estado Atual do Sistema
- **Crawler**: Ativo no projeto `FoxOT`.
- **Persistência**: Operacional via PostgreSQL + pgvector (tabelas isoladas).
- **Dashboard**: Funcional e exibindo dados reais da indexação em background.

---

## 🚀 Planejamento para a Próxima Sessão

### A. Validação do Batch Indexing
- Confirmar a conclusão dos 10k arquivos do FoxOT e verificar se o `batch_progress.json` marcou o projeto como concluído.
- Iniciar a indexação do projeto `Rust Star` (Engine) se ainda não tiver sido concluída.

### B. Implementação de "Metadata Enrichment"
- Conforme registrado em `SUGGESTIONS.md`, implementar a categorização automática por caminho de diretório (ex: monster, spell, engine) para melhorar a precisão do RAG.

### C. Refinamento de Busca (RAG)
- Realizar testes de estresse na busca vetorial agora que a base de dados possui milhares de fragmentos, ajustando os parâmetros de `top-N` se necessário.

---
> [!IMPORTANT]
> **Nota para a Próxima Sessão**: Antes de qualquer ação, consulte este diário e os documentos em `docs/` para manter a integridade da arquitetura alcançada.
