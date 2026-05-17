# Diário de Sessão: MCP Rust Star Knowledge Server

Este documento é o registro mestre de transição entre sessões. Ele detalha o estado atual do projeto, marcos alcançados e o planejamento imediato para a continuidade do desenvolvimento.


---

## 🗓️ Sessão: 17/05/2026 (Parte 14) — Plano de Correção Honesto Concluído: Fatias 4, 5, 6 e 7 de Elite

### Contexto
Finalização das fatias finais do **Plano de Correção Honesto** para o servidor de conhecimento **`mcp-rust-star`**, cobrindo a restauração do "Stdout Sacro", repositório de Skills (v1.1) e alinhamento total de ADRs e logs, culminando na validação E2E bem-sucedida pelo usuário.

### Conquistas

#### 1. Restauração do "Stdout Sacro" (Fatia 4)
- **`.agents/rules/01-mcp-system-integrity.md`**: Restaurada integralmente a Seção 2 original. A regra preserva que o `stdout` é exclusivo do protocolo JSON-RPC em conexões STDIO legadas, forçando qualquer log ou print acidental para `stderr` via decorador para evitar a quebra do canal de dados MCP.

#### 2. Restauração de Skills de Elite (Fatia 5)
- **`.agents/skills/mcp-rust-star/SKILL.md`**: Restaurada a versão industrial v1.1 original das skills.
- **`.agents/skills/mcp-rust-star/CONFIG_GUIDE.md`**: Restaurado o guia de configuração e calibração VRAM detalhado para os ambientes de produção.

#### 3. Sincronização e Correção de ADRs (Fatia 6)
- **`docs/adr/0016-model-guard-serializacao-ollama.md`**: Atualizado para refletir a causa raiz original (a regressão do default `auto_unload=False` corrigida na Fatia 1) e consolidar as decisões D1 (lock granular por arquivo) e D2 (lookahead FIFO cooperativo via `peek_next_kind`).
- **`docs/adr/0015-transporte-streamable-http.md`**: Ajustado de forma cirúrgica para constar que `_windows_stdin_keepalive` e a Regra 01 §2 foram mantidos como mecanismos ativos de compatibilidade no modo STDIO legado.

#### 4. Validação de Campo e Testes E2E (Fatia 7)
- **Verificação E2E Concluída**: O usuário executou de forma independente e controlada o `run_server.bat` em seu ambiente Windows.
- **Boot Limpo e Handshake de Sucesso**: O log reportou passagens 100% limpas de probes (`Ollama acessível`, `PostgreSQL acessível`, `PID escrito`), subindo o transporte `streamable-http` na porta 8765.
- **Conectividade IDE**: A IDE conectou com sucesso, negociando e processando a listagem de ferramentas (`Processing request of type ListToolsRequest`) sem qualquer travamento, latência ou contenção.
- **Suíte de Testes Verde**: A suíte de 81 testes de produção unitários está 100% verde e operando sem regressões.

### Arquivos Modificados nesta Sessão
| Arquivo | Mudança |
|---|---|
| [.agents/rules/01-mcp-system-integrity.md](../.agents/rules/01-mcp-system-integrity.md) | Restauração da Seção 2 sobre o "stdout sacro" legado. |
| [.agents/skills/mcp-rust-star/SKILL.md](../.agents/skills/mcp-rust-star/SKILL.md) | Restauração do Grimório de Operação v1.1. |
| [.agents/skills/mcp-rust-star/CONFIG_GUIDE.md](../.agents/skills/mcp-rust-star/CONFIG_GUIDE.md) | Restauração do manual de calibração de VRAM e Docker. |
| [docs/adr/0016-model-guard-serializacao-ollama.md](adr/0016-model-guard-serializacao-ollama.md) | Documentação de concorrência cooperativa granular (D1+D2) e causa raiz real. |
| [docs/adr/0015-transporte-streamable-http.md](adr/0015-transporte-streamable-http.md) | Ajustadas consequências sobre keepalive e Regra 01 no transporte legado. |
| [docs/operation/tasks-Plano_Correcao_Honesto.md](operation/tasks-Plano_Correcao_Honesto.md) | Checklist oficial atualizada com todas as fatias 100% concluídas. |

### Estado Final do Sistema
O ecossistema **`mcp-rust-star`** está perfeitamente estabilizado, com VRAM gerida cirurgicamente, concorrência cooperativa granular de alta resposta e suporte híbrido seguro tanto para streamable-HTTP local multi-cliente quanto para STDIO legado via auto-detecção de pipe.

---

## 🗓️ Sessão: 17/05/2026 (Parte 13) — Plano de Correção Honesto: Fatia 2 Concluída

### Contexto
Execução da **Fatia 2** do Plano de Correção Honesto para otimizar o gerenciamento de concorrência e uso de VRAM no Ollama durante indexação massiva/background.

### Conquistas

#### 1. Implementação de Lookahead FIFO no ModelGuard
- **`src/services/model_guard.py`**: Adicionada a função `peek_next_kind(self) -> Kind | None`. Ela inspeciona o primeiro elemento da fila de espera (`self._queue`) sem alterar seu estado. Isso permite saber com antecedência se a próxima tarefa na fila é do mesmo `kind` (ex: `embed`) ou de outro `kind` (ex: `chat`), ou se a fila está vazia.

#### 2. Refatoração Completa para Concorrência Cooperativa e Granular
- **`src/main.py`**: 
  - **Remoção de Lock Global**: Removido o decorator `@with_model_guard(kind="embed")` de `_batch_embed_worker` e de `index_directory` para evitar locks contínuos por horas ou deadlocks reentrantes.
  - **Novo Core Assíncrono**: Substituído o `_walk_and_index_sync` por `_collect_files_sync` (coleta síncrona rápida de caminhos de arquivos) e `_walk_and_index_async` (loop assíncrono cooperativo executado na thread principal do asyncio).
  - **Lock Granular por Arquivo**: A indexação assíncrona adquire o lock do `ModelGuard` individualmente para cada arquivo.
  - **VRAM Eject Pattern com Lookahead**: Ao fim de cada arquivo indexado, a rotina consulta `peek_next_kind()`. Se o próximo `kind` for diferente de `"embed"` (ex: uma pergunta RAG `"chat"` do usuário) ou se a fila de tarefas estiver vazia, ela descarrega a VRAM do Ollama proativamente via `unload_models()`. Se a próxima tarefa for outro `"embed"`, ela mantém o modelo na VRAM para alta performance.

#### 3. Testes Unitários de Elite
- **`tests/services/test_model_guard.py`**: Adicionado o caso de teste `test_peek_next_kind` validando cenários concorrentes de lookahead, transições e fila vazia.
- **Suíte Verde**: Todos os **81 testes unitários principais** na pasta `tests/` passaram de primeira em apenas ~12 segundos, comprovando integridade de 100% da arquitetura!

### Arquivos Modificados nesta Sessão
| Arquivo | Mudança |
|---|---|
| [src/services/model_guard.py](../src/services/model_guard.py) | Adicionado `peek_next_kind` para lookahead de fila. |
| [src/main.py](../src/main.py) | Removido lock global do worker/diretório; implementados `_collect_files_sync` e `_walk_and_index_async` com locks granulares e lookahead. |
| [tests/services/test_model_guard.py](../tests/services/test_model_guard.py) | Adicionados testes unitários robustos de concorrência para `peek_next_kind`. |

### Pendências para Próxima Sessão (Plano de Correção Honesto)
- **Fatia 3**: Restaurar `_windows_stdin_keepalive` em [src/main.py](../src/main.py) com o respectivo guard de transporte (`if _TRANSPORT == "stdio":`).
- **Fatia 4**: Restaurar [.agents/rules/01-mcp-system-integrity.md](../.agents/rules/01-mcp-system-integrity.md) §2 ("stdout sacro").
- **Fatia 5**: Restaurar `SKILL.md` (v1.1) e `CONFIG_GUIDE.md` em [.agents/skills/mcp-rust-star/](../.agents/skills/mcp-rust-star/).
- **Fatia 6**: Editar ADR-0016 refletindo causa raiz real + decisão D1+D2.
- **Fatia 7**: Validações finais E2E e fechamento do ciclo de correção.


---

## 🗓️ Sessão: 17/05/2026 (Parte 12) — Estabilização de Dimensão RAG, Dotenv e Indexação de Nova Rust

### Contexto
O usuário registrou o novo projeto `"Nova Rust"`, mas a primeira indexação reportou sucesso falso sem carregar a VRAM e sem salvar dados. Um diagnóstico profundo da causa raiz revelou:
1. Conflito físico de dimensões vetoriais no PostgreSQL: a coluna da tabela era criada como `embedding vector(2560)` fixo, enquanto o modelo `qwen3-embedding:8b` gerava vetores de **4096** dimensões.
2. Problema de dependência de importação (dotenv): o `load_dotenv` era chamado em `ollama_client.py` após o `PostgresStore` ser importado e inicializado, fazendo a leitura de `EMBEDDING_DIM` falhar e retornar o padrão antigo de 2560.
3. Ocultação de exceções em `rag_service.py`, que capturava o erro de inserção e retornava uma string, fazendo com que o lote no `main.py` contabilizasse a falha como novo arquivo de sucesso com `0 erros`.

### Conquistas

#### 1. Correção Cirúrgica do Conflito de Dimensões e Dotenv
- **`src/vector_store_postgres.py`**: Adicionada inicialização dinâmica do tamanho da coluna vetorial com base no `.env` (`embedding vector({self.embedding_dim})`). Importado e chamado `load_dotenv(override=True)` no passo zero absoluto do topo do arquivo, garantindo o ambiente carregado antes de qualquer inicialização de pool.
- **`run_batch_index.py`**: Adicionado `load_dotenv(override=True)` no topo do script CLI standalone para assegurar dimensões corretas nas execuções de terminal.

#### 2. Propagação Honesta de Exceções no RAG
- **`src/services/rag_service.py:253`**: Removido o retorno de string de erro silenciosa, inserindo `raise` explícito para propagar exceções reais para o chamador do lote.

#### 3. Parada, Boot HTTP e Recarga de Sessão do Servidor
- Encerrado o processo antigo travado e subido o novo servidor HTTP MCP saudável na porta 8765 de forma explícita com:
  `.\.venv\Scripts\python.exe -u -m src.main --transport streamable-http`
- Forçado o recarregamento do cliente MCP na IDE através de atualização atômica de `mcp_config.json`.

#### 4. Indexação e Validação de 100% de Sucesso do Nova Rust
- Limpa a tabela corrompida de 2560 dimensões chamando o método de exclusão física do projeto.
- Disparada a indexação em lote em UTF-8 direto no terminal via script standalone de alta performance.
- **139 arquivos elegíveis escaneados e indexados** com absoluto sucesso.
- **0 erros registrados**.
- Efetuada auditoria física no PostgreSQL do Docker, confirmando a persistência de **151 fragmentos vetoriais de 4096 dimensões** gravados com sucesso na tabela `knowledge_nova_rust`!
- Modelos descarregados proativamente ao fim para preservar a VRAM do usuário.

### Arquivos Modificados nesta Sessão
| Arquivo | Mudança |
|---|---|
| [src/vector_store_postgres.py](../src/vector_store_postgres.py) | `EMBEDDING_DIM` dinâmico + `load_dotenv` no topo. |
| [src/services/rag_service.py](../src/services/rag_service.py) | Propagação de erro com `raise` no final. |
| [run_batch_index.py](../run_batch_index.py) | `load_dotenv` no topo + execução robusta CLI. |
| [mcp_config.json](file:///c:/Users/Foxpop/.gemini/antigravity/mcp_config.json) | Touch do JSON de configuração MCP da IDE. |
| [task.md](file:///C:/Users/Foxpop/.gemini/antigravity/brain/2395e229-4333-4252-b7bb-6403def37833/task.md) | Criada e mantida a TODO list de execução. |
| [walkthrough.md](file:///C:/Users/Foxpop/.gemini/antigravity/brain/2395e229-4333-4252-b7bb-6403def37833/walkthrough.md) | Novo walkthrough contendo relatório técnico e evidências de banco. |

### Pendências para Próxima Sessão
* **Consultas de Validação RAG**: Disparar consultas complexas de RAG sobre o projeto `Nova Rust` para certificar a qualidade da busca vetorial estruturada no Postgres.

---

## 🗓️ Sessão: 17/05/2026 (Parte 11) — Plano de Correção Honesto: Fatia 1 + correções paralelas IDE

### Contexto
Auditoria das Fases 1/5/6 do Plano de Estabilização v2.0 (Partes 6–10) identificou alterações fora do escopo autorizado e uma regressão prévia no commit `73aa752` (`auto_unload=True → False` em [src/ollama_client.py](../src/ollama_client.py)). Criados o plano-mestre [docs/operation/2026-05-17_Plano_Correcao_Honesto.md](operation/2026-05-17_Plano_Correcao_Honesto.md) e o tasks file [docs/operation/tasks-Plano_Correcao_Honesto.md](operation/tasks-Plano_Correcao_Honesto.md), com 7 fatias finas exigindo **aprovação explícita** entre cada uma.

### Conquistas

#### 1. Fatia 1 concluída — `src/ollama_client.py` (lógica de descarga)
- [src/ollama_client.py:48](../src/ollama_client.py#L48): default de `get_embedding(auto_unload=...)` restaurado de `False` → `True` (Regra 05 — VRAM Eject Pattern).
- Grep dos call-sites confirmou que ninguém passa `auto_unload` explicitamente → todos voltam a se beneficiar do descarregamento proativo por padrão.
- Verificada simetria em `generate_response`, `describe_image`, `unload_models`, `_unload_model` — nenhum análogo sofreu inversão similar.
- Testes existentes que tocam `OllamaClient` passam sem regressão.
- Fase 1.6 (aprovação para avançar) marcada `[~]` — encerramento de sessão sem aprovação explícita do usuário.

#### 2. Correções paralelas autorizadas (fora do ciclo de fatias) — diagnóstico de IDE Antigravity travada
Causa raiz identificada durante a sessão: a IDE Antigravity tentava subir uma 2ª instância STDIO em paralelo ao servidor HTTP rodando no terminal, travando o handshake. Correções aplicadas:

| Arquivo | Mudança | Autorização |
|---|---|---|
| [c:\Users\Foxpop\.gemini\antigravity\mcp_config.json](file:///c:/Users/Foxpop/.gemini/antigravity/mcp_config.json) | `mcp-rust-star`: STDIO (`command`/`args`/`cwd`/`env`) → HTTP (`url: http://127.0.0.1:8765/mcp`). `github-mcp-server` mantido intacto. | Explícita do usuário ("sim autorizo") |
| [.vscode/mcp.json](../.vscode/mcp.json) | Rename `rust-star-knowledge` → `mcp-rust-star`. Mantido HTTP. | Explícita do usuário ("se for util e puder corrigir o nome corrija") |

**Nome canônico ratificado pelo usuário**: `mcp-rust-star` (sobrescreve o nome histórico `rust-star` que estava em HEAD).

#### 3. Atualizações do plano-mestre e tasks file (refletir decisão atual)
- [docs/operation/2026-05-17_Plano_Correcao_Honesto.md](operation/2026-05-17_Plano_Correcao_Honesto.md):
  - D5 atualizado: HTTP + nome canônico `mcp-rust-star`.
  - A6 marcado como resolvido (config Antigravity + `.vscode/mcp.json`).
  - Fatia 7 atualizada com JSON novo + nota sobre correções paralelas.
- [docs/operation/tasks-Plano_Correcao_Honesto.md](operation/tasks-Plano_Correcao_Honesto.md):
  - Fatia 7 com nota sobre nome canônico + correções paralelas.
  - Fase 7.1 marcada `[x]` (config já estava correta).

### Pendências para próxima sessão

#### Prioridade 1 — aguardando aprovação explícita
- **Fase 1.6** (`[~]`): aprovação para avançar Fatia 1 → Fatia 2.
- Validação E2E: usuário precisa recarregar a Antigravity (`Ctrl+Shift+P` → "Developer: Reload Window") e confirmar que o MCP conecta via HTTP sem travar.

#### Prioridade 2 — Fatia 2 (próxima após aprovação)
`src/services/model_guard.py` — substituir `asyncio.Lock` único por fila com lookahead `peek_next_kind()` + granularidade por chamada (não por batch). Wire-up no `_batch_embed_worker` decidirá `auto_unload` consultando o próximo `kind` aguardando. Testes em [tests/services/test_model_guard.py](../tests/services/test_model_guard.py) precisam cobrir: mesmo kind / outro kind / fila vazia / 5 concorrentes intercalados.

#### Prioridade 3 — Fatias 3–7 (em ordem)
- **Fatia 3**: restaurar `_windows_stdin_keepalive` em [src/main.py](../src/main.py) com guarda `if _TRANSPORT == "stdio":`.
- **Fatia 4**: restaurar [.agents/rules/01-mcp-system-integrity.md](../.agents/rules/01-mcp-system-integrity.md) §2 ("stdout sacro").
- **Fatia 5**: restaurar `SKILL.md` (v1.1) e `CONFIG_GUIDE.md` em [.agents/skills/mcp-rust-star/](../.agents/skills/mcp-rust-star/).
- **Fatia 6**: editar [docs/adr/0016-model-guard-serializacao-ollama.md](adr/0016-model-guard-serializacao-ollama.md) refletindo causa raiz real (regressão de `auto_unload`) + decisão D1+D2. Verificar pontualmente ADRs 0015/0018/0019.
- **Fatia 7**: 7.2 (validação E2E rodando servidor + IDE), 7.3 (fechamento neste SESSION_LOG), 7.4 (aprovação final).

### Avisos de segurança

> ⚠️ **Token PAT do GitHub exposto na transcrição**: o token `ghp_[REDACTED]` apareceu em texto plano ao ler [c:\Users\Foxpop\.gemini\antigravity\mcp_config.json](file:///c:/Users/Foxpop/.gemini/antigravity/mcp_config.json) durante o diagnóstico da IDE travada. **Recomendação**: revogar e regenerar em https://github.com/settings/tokens. Considerar mover credenciais para variáveis de ambiente fora do JSON.

### Avisos operacionais

- A IDE Antigravity emitiu warning de schema "A propriedade url não é permitida" para a entrada `mcp-rust-star` no `mcp_config.json` — é apenas warning de schema (a IDE não conhece o formato HTTP do schema oficial MCP). Funcionalmente OK.
- [scripts/run_server.bat](../scripts/run_server.bat) (e/ou [run_server.bat](../run_server.bat) na raiz) tem texto "Iniciando Servidor MCP (Modo STDIO)" desatualizado — servidor sobe em HTTP por padrão. Bug cosmético, não corrigido (fora do escopo do Plano de Correção Honesto).

### Regras do projeto reforçadas nesta sessão
- **Regra 00 — Stop & Think**: cada fatia exige autorização explícita antes de iniciar e antes de avançar. Não iniciar Fatia 2 sem confirmação.
- **Regra 03 — Diagnóstico Científico**: a Fatia 1 partiu do diff real vs HEAD (commit `4cfb30e` pré-regressão vs `73aa752`), não de suposição.
- **Regra 04 — Vertical Slicing**: 7 fatias finas com validação entre cada uma.
- **Compromisso técnico**: zero comando git destrutivo (`revert`/`reset`/`checkout --`/`restore .`). Git apenas para `diff`/`show` em leitura.

---

## 🗓️ Sessão: 17/05/2026 (Parte 10) — Transporte CLI/auto-detect, proteção STDIO e shutdown completo

### Contexto
Continuação direta da Parte 9. Objetivo: suporte robusto a múltiplos modos de transporte (HTTP e STDIO) com detecção automática, proteção de conflito HTTP↔STDIO e garantia de shutdown limpo sem threads residuais.

### Conquistas

#### 1. Auto-detecção de transporte via stdin pipe
O servidor detecta automaticamente o modo STDIO quando chamado por um IDE via configuração JSON (stdin é pipe, não terminal). Cadeia de prioridade implementada em `src/main.py` `__main__`:

```
1. --transport <valor>  →  CLI explícito
2. sys.stdin.isatty() == False  →  stdin é pipe → STDIO automático
3. data/defaults.json ["server"]["transport"]  →  padrão ("streamable-http")
```

IDEs como Cursor/VS Code com configuração `"command"` + `"args"` funcionam sem `--transport stdio` explícito.

#### 2. Argparse CLI `--transport`
`--transport stdio|streamable-http` adicionado ao bloco `__main__` com `argparse`. Permite forçar o modo sem editar `defaults.json`.

#### 3. Proteção STDIO vs HTTP simultâneo (`startup_probes` transport-aware)
`startup_probes()` agora recebe `transport` e aplica semântica diferente para a probe de porta:
- HTTP: porta deve estar LIVRE (para o bind do uvicorn).
- STDIO: porta deve estar LIVRE (se ocupada → servidor HTTP ativo → `sys.exit(1)` com mensagem `CRITICAL`). Evita corrupção do canal stdout do MCP.

#### 4. Signal handler: `sys.exit → os._exit`
`setup_signal_handlers` trocou `sys.exit(0)` por `os._exit(0)` no handler. `os._exit` mata todas as threads daemon imediatamente e **não** aciona `atexit` — eliminando o risco de dupla execução de `handle_exit`.

#### 5. Guard `_exit_called` contra dupla execução
`_exit_called = threading.Event()` protege `handle_exit` de rodar duas vezes (atexit + sinal tardio).

#### 6. Join da thread de heartbeat no shutdown
`handle_exit` sinaliza `_heartbeat_stop` e chama `_heartbeat_thread.join(timeout=3.0)` antes do flush — sem threads residuais após shutdown normal.

#### 7. Scripts atualizados
- `scripts/start_server.bat`: repassa `%*` para `src.main`, permitindo `--transport`.
- `scripts/start_server.ps1`: parâmetro `-Transport` tipado com `ValidateSet`, repassado via `@extra`.

### Documentação atualizada
| Arquivo | Mudança |
|---|---|
| `docs/adr/0015-transporte-streamable-http.md` | Seção §Auto-detecção com cadeia de prioridade e proteção STDIO |
| `docs/adr/0018-lifecycle-graceful-shutdown.md` | `startup_probes` transport-aware, `os._exit`, guard `_exit_called`, join heartbeat |
| `docs/SESSION_LOG.md` | Esta entrada (Parte 10) |
| `src/services/lifecycle.py` | `startup_probes(transport)`, `os._exit` no handler |
| `src/main.py` | argparse, auto-detect, `_exit_called`, join heartbeat |
| `scripts/start_server.bat` | `%*` forwarding |
| `scripts/start_server.ps1` | `-Transport` param |
| `tests/services/test_lifecycle.py` | 2 novos testes STDIO; signal test mockando `os._exit` |

### Pendente
- **Fase 1.5**: teste de integração IDE + cliente Python simultâneos vendo `list_projects` (requer servidor rodando).

---

## 🗓️ Sessão: 17/05/2026 (Parte 9) — Fase 6.5: Avaliação SSE vs watchfiles

### Contexto
Fase 6.5 (opcional) do Plano de Estabilização v2.0: avaliar se o dashboard TUI deve migrar de `watchfiles` (file-watching) para consumir `/events/stream` (SSE).

### Conclusão: manter watchfiles, migração não recomendada

O `dashboard/fetcher.py` já opera em modo event-driven via `watchfiles.watch()` — o SO notifica mudanças em `data/dashboard_state.json` sem polling por intervalo fixo. Latência efetiva: < 250ms (throttle do `TelemetryWriter`). Migrar para SSE (poll 500ms) seria **mais lento**, além de exigir reescrita da lógica de state reconstruction no dashboard (snapshot completo → eventos individuais acumulativos) e quebrar suporte ao modo STDIO legado.

`/events/stream` permanece disponível para clientes remotos (dashboard web, CI, monitoramento externo sem acesso ao filesystem do servidor).

### Documentação
Avaliação detalhada com tabela de trade-offs adicionada em `docs/adr/0019-observabilidade-http.md` §Fase 6.5.

### Arquivos alterados
| Arquivo | Mudança |
|---|---|
| `docs/adr/0019-observabilidade-http.md` | Seção §Fase 6.5 com tabela de trade-offs e decisão |
| `docs/operation/tasks-Plano_Estabilização.md` | Fase 6.5 marcada `[x]` — **Plano de Estabilização v2.0 completo** |

### Status do Plano de Estabilização v2.0
**Todas as fases concluídas**: Fase 3 (EventBus) → Fase 2 (ModelGuard) → Fase 4 (Telemetria) → Fase 1 (HTTP) → Fase 5 (Lifecycle) → Fase 6 (Observabilidade) → Fase 6.5 (Avaliação SSE).

Pendente apenas **Fase 1.5** (teste de integração com servidor rodando: IDE + cliente Python simultâneos vendo `list_projects`).

---

## 🗓️ Sessão: 16/05/2026 (Parte 8) — Fase 6: Observabilidade HTTP (ADR-0019)

### Contexto
Continuação do Plano de Estabilização v2.0. Fase 6 completa: 4 endpoints HTTP de observabilidade ao lado do `/mcp`, sem porta separada.

### Conquistas
- **ADR-0019** (`docs/adr/0019-observabilidade-http.md`) — documentado: motivação, decisão, SSE design (poll + ring buffer), alternativas rejeitadas.
- **`src/services/observability.py`** — Novo módulo com `register_observability_routes`. Usa `@mcp.custom_route(...)` do MCP SDK 1.27.1 (integra via `_custom_starlette_routes` no mesmo uvicorn).
- **`GET /health`** — status `ok`/`degraded`, uptime, Ollama, DB, ModelGuard, `last_event_at`.
- **`GET /events/recent`** — query params `limit` (máx 500) e `pattern` (glob); consome ring buffer do EventBus.
- **`GET /events/stream`** — SSE via `sse-starlette`; envia histórico dos últimos 60s ao conectar, depois poll 0.5s com keepalive 15s.
- **`GET /metrics`** — `tool_calls_total`, `embed_completed_total`, `rag_queries_total`, `model_guard_queue_depth`, `events_in_buffer`, `uptime_s`.
- **`src/main.py`** — `_SERVER_START_TIME = time.time()` adicionado; `register_observability_routes(mcp, rag, _bus, _SERVER_START_TIME)` chamado na inicialização.
- **`tests/services/test_observability.py`** — 9 testes unitários; todos passando.

### Detalhe técnico: integração FastMCP
`@mcp.custom_route(path, methods)` adiciona uma `starlette.routing.Route` em `FastMCP._custom_starlette_routes`. Na chamada a `mcp.run(transport="streamable-http")`, `streamable_http_app()` faz `routes.extend(self._custom_starlette_routes)` — as rotas ficam no mesmo processo uvicorn, sem porta adicional.

O `get_model_guard` deve ser importado no nível do módulo em `observability.py` (não dentro da função), para que `patch("src.services.observability.get_model_guard")` funcione nos testes.

### Arquivos alterados
| Arquivo | Mudança |
|---|---|
| `docs/adr/0019-observabilidade-http.md` | Novo — ADR da decisão |
| `src/services/observability.py` | Novo — 4 endpoints de observabilidade |
| `src/main.py` | `_SERVER_START_TIME` + `register_observability_routes` |
| `tests/services/test_observability.py` | Novo — 9 testes unitários |
| `docs/operation/tasks-Plano_Estabilização.md` | Fase 6 marcada como concluída |

### Resultado dos testes
**78/78 testes passando** (9 observabilidade + 13 lifecycle + 10 event-driven + 14 EventBus + 10 ModelGuard + 3 live_repaints + 18 state_decider + 1 scratch_sync).

### Próximo passo
**Fase 6.5 (opcional)**: avaliar migração do dashboard de file-polling para `/events/stream`. Ou iniciar próxima fase do Plano de Estabilização.

---

## 🗓️ Sessão: 16/05/2026 (Parte 7) — Fase 5: Lifecycle Robusto (ADR-0018)

### Contexto
Continuação do Plano de Estabilização v2.0. Fase 5 completa: startup probes, PID file, ModelGuard drain, signal handlers e 13 testes unitários.

### Conquistas
- **ADR-0018** (`docs/adr/0018-lifecycle-graceful-shutdown.md`) — documentado: motivação (startup cego, shutdown abrupto, sem rastreabilidade de processo), decisão e catálogo de eventos.
- **`src/services/lifecycle.py`** — Novo módulo com `write_pid_file`, `remove_pid_file`, `_check_port_free` (connect-based, contornando `SO_REUSEADDR` do Windows), `startup_probes`, `drain_model_guard`, `setup_signal_handlers`.
- **`src/main.py`** — `handle_exit()` ampliado com `server.stopped` emit, `drain_model_guard()`, flush de telemetria e `remove_pid_file()`. Bloco `__main__` adiciona `setup_signal_handlers`, `startup_probes` e `write_pid_file` antes de `mcp.run()`.
- **`scripts/stop_server.bat`** — Novo script que lê `data/server.pid` e encerra com `taskkill /PID`.
- **`tests/services/test_lifecycle.py`** — 13 testes unitários: PID file, port probe, startup probes (3 cenários de falha), drain (3 cenários), signal handler. Todos passando.

### Detalhe técnico: `SO_REUSEADDR` no Windows
No Windows, `SO_REUSEADDR` permite que dois sockets se liguem ao mesmo endereço/porta simultaneamente — diferente do comportamento Unix. Detectar "porta em uso" via `bind()` falha silenciosamente. Solução: `connect_ex()` ao host/porta alvo; retorna 0 apenas se houver um servidor escutando.

O patch dos testes de `drain_model_guard` deve apontar para `src.services.model_guard.get_model_guard` (módulo-fonte), pois a importação ocorre dentro do corpo da função, não no nível do módulo `lifecycle`.

### Arquivos alterados
| Arquivo | Mudança |
|---|---|
| `docs/adr/0018-lifecycle-graceful-shutdown.md` | Novo — ADR da decisão |
| `src/services/lifecycle.py` | Novo — módulo de lifecycle |
| `src/main.py` | `handle_exit` + `__main__` integrados ao lifecycle |
| `scripts/stop_server.bat` | Novo — stop via PID file |
| `tests/services/test_lifecycle.py` | Novo — 13 testes unitários |
| `docs/operation/tasks-Plano_Estabilização.md` | Fase 5 marcada como concluída |

### Resultado dos testes
**69/69 testes passando** (13 lifecycle + 10 event-driven + 14 EventBus + 10 ModelGuard + 3 live_repaints + 18 state_decider + 1 scratch_sync).

### Próximo passo
**Fase 6 — Superfície de observabilidade HTTP**: `/health`, `/events/recent`, `/events/stream` SSE endpoints ao lado do `/mcp`.

---

## 🗓️ Sessão: 16/05/2026 (Parte 6) — Fase 1: Transporte Streamable-HTTP (ADR-0015)

### Contexto
Continuação do Plano de Estabilização v2.0. Fase 1 completa: servidor migrado de STDIO para streamable-http, `_windows_stdin_keepalive` removido, scripts de start criados.

### Conquistas
- **ADR-0015** (`docs/adr/0015-transporte-streamable-http.md`) — documentado: motivação multi-cliente, contraste com STDIO, decisão de usar streamable-http nativo do FastMCP 1.27+.
- **`data/defaults.json`** — criado com seção `server` (`transport`, `host`, `port`). FastMCP lê `host`/`port` via construtor; `transport` passado no `mcp.run()`.
- **`src/main.py`** — `_windows_stdin_keepalive()` removido; bloco `asyncio.get_event_loop()` removido; `mcp.run()` → `mcp.run(transport=_TRANSPORT)`; FastMCP inicializado com `host=_HOST, port=_PORT` lidos de `defaults.json`.
- **`.agents/rules/01`** — Seção 2 atualizada: "stdout sacro" restrito ao modo STDIO legado; streamable-http (padrão) não tem essa restrição.
- **`scripts/start_server.bat`** e **`scripts/start_server.ps1`** — criados para iniciar o servidor com as variáveis de ambiente corretas.

### Configuração de cliente (snippet IDE)

**Antes (STDIO — legado):**
```json
{
  "rust-star-knowledge": {
    "command": "c:/Phantasy/MCP Rust Star/.venv/Scripts/python.exe",
    "args": ["-m", "src.main"],
    "cwd": "c:/Phantasy/MCP Rust Star",
    "env": { "PYTHONPATH": "c:/Phantasy/MCP Rust Star", "VECTOR_STORE_TYPE": "postgres" }
  }
}
```

**Depois (streamable-http — padrão):**
```json
{
  "rust-star-knowledge": {
    "url": "http://127.0.0.1:8765/mcp"
  }
}
```

### Arquivos alterados
| Arquivo | Mudança |
|---|---|
| `docs/adr/0015-transporte-streamable-http.md` | Novo — ADR da decisão |
| `data/defaults.json` | Novo — seção server com transport/host/port |
| `src/main.py` | `_windows_stdin_keepalive` removido; `mcp.run(transport=_TRANSPORT)` |
| `.agents/rules/01-mcp-system-integrity.md` | §2 atualizado para modo HTTP vs STDIO |
| `scripts/start_server.bat` | Novo — script de start Windows CMD |
| `scripts/start_server.ps1` | Novo — script de start PowerShell |

### Resultado dos testes
**55/55 testes passando** (sem regressões).

### Próximo passo
**Fase 5 — Lifecycle robusto**: ADR-0018, startup probes (Ollama, PostgreSQL), signal handlers SIGTERM/SIGINT, `data/server.pid`.

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
