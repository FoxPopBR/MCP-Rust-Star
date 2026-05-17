# ADR-0018: Lifecycle Robusto — Startup Probes e Graceful Shutdown

O servidor MCP Rust Star inicializava sem verificar a disponibilidade de Ollama ou PostgreSQL, e encerrava sem drenar o ModelGuard ou emitir eventos de ciclo de vida. Isso tornava falhas de startup silenciosas e o shutdown potencialmente corrupto (embedding interrompido no meio).

## Contexto

Três problemas concretos:

1. **Startup cego**: o servidor subia e aceitava conexões MCP mesmo com Ollama offline ou PostgreSQL inacessível. As ferramentas falhavam na primeira chamada com erros crípticos em vez de falhar claramente na inicialização.
2. **Shutdown abrupto**: `atexit.register(handle_exit)` já existia, mas não drenava o ModelGuard — se um embedding estivesse em curso, o lock era abandonado. Sem emissão de `server.stopped`, o dashboard não detectava o encerramento via EventBus.
3. **Sem rastreabilidade de processo**: sem `data/server.pid`, scripts externos não conseguem identificar o PID do servidor para enviar sinais de controle.

## Decisão

Implementar `src/services/lifecycle.py` com:

- **Startup probes** (`startup_probes(rag, bus, host, port, transport)`): verifica porta livre, Ollama e PostgreSQL antes de `mcp.run()`. Emite `server.starting` antes das probes e `server.started` após. Chama `sys.exit(1)` (fail-fast) se qualquer probe falhar. A semântica da probe de porta é **transport-aware**:
  - HTTP: porta deve estar LIVRE para o bind do uvicorn.
  - STDIO: porta deve estar LIVRE — se ocupada, um servidor HTTP está ativo e rodar STDIO simultâneo corromperia o canal stdout do MCP.
- **PID file** (`write_pid_file()` / `remove_pid_file()`): escreve o PID em `data/server.pid` no startup; remove no `handle_exit()`.
- **ModelGuard drain** (`drain_model_guard()`): polling de até 5s aguardando o lock liberar antes do shutdown. Continua mesmo se timeout estourar — apenas loga warning.
- **Signal handlers** (`setup_signal_handlers(exit_fn)`): registra SIGINT e SIGTERM (se disponível no Windows) para chamar `exit_fn()` e `os._exit(0)`. Usa `os._exit` (não `sys.exit`) para matar threads daemon imediatamente sem acionar handlers `atexit`.

### Proteção contra execução dupla de `handle_exit`

`handle_exit` é registrado tanto via `atexit.register()` quanto via `setup_signal_handlers()`. Sem proteção, um sinal recebido durante execução normal de `mcp.run()` chamaria `handle_exit` pelo signal handler e novamente pelo atexit ao sair — causando duplo flush de telemetria e duplo `remove_pid_file`.

A proteção usa `_exit_called = threading.Event()` em `src/main.py`:

```python
_exit_called = threading.Event()

def handle_exit():
    if _exit_called.is_set():
        return
    _exit_called.set()
    # ... flush, drain, join, remove_pid_file
```

No caminho do sinal, `os._exit(0)` encerra o processo antes de o atexit ser acionado — a dupla execução nunca ocorre. O guard protege o caminho normal (`mcp.run()` retorna → atexit roda → sinal chega tarde).

### Cleanup completo de threads no shutdown

`handle_exit` sinaliza a thread de heartbeat e aguarda sua finalização antes do flush:

```python
_heartbeat_stop.set()
if _heartbeat_thread is not None and _heartbeat_thread.is_alive():
    _heartbeat_thread.join(timeout=3.0)
```

No caminho do sinal, `os._exit(0)` mata todas as threads (daemon e não-daemon) imediatamente — o join é irrelevante nesse caso, mas não prejudica.

## Catálogo de eventos emitidos

| Evento | Quando |
|--------|--------|
| `server.starting` | Antes das probes de startup |
| `server.started` | Após todas as probes passarem |
| `server.stopped` | Em `handle_exit()`, antes do flush final |

## Alternativas consideradas

- **Probes via thread daemon**: executar probes enquanto o servidor já está subindo. Descartado — o FastMCP não expõe hook de "pronto para aceitar conexões"; clientes receberiam erros enquanto as probes rodam.
- **Retry automático de Ollama**: aguardar até 30s por disponibilidade. Descartado para a v1 — aumenta complexidade sem ganho imediato; o operador pode reiniciar o servidor quando Ollama estiver pronto.
- **Supervisão de processo (systemd / NSSM)**: delegar restart ao supervisor. Válido em produção, mas não elimina a necessidade de probes — apenas muda quem gerencia o retry.

## Consequências

- Falhas de infraestrutura (Ollama offline, Postgres inacessível, porta em uso) são detectadas em < 2s com mensagem `CRITICAL` clara.
- `data/server.pid` permite `scripts/stop_server.bat` encerrar o servidor com precisão.
- Shutdown garante flush da telemetria e dreno do ModelGuard antes de sair — sem corrupção de estado.
- `server.started` / `server.stopped` no EventBus permitem que os endpoints `/health` e `/events/stream` (Fase 6) reflitam o estado real do servidor.
