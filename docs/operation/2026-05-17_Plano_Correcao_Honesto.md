# Plano de Correção Honesto — MCP Rust Star

**Data**: 2026-05-17
**Autor**: Sessão Claude Opus 4.7 (sob revisão de FoxPop)
**Status**: Aprovado para execução

## Contexto

Auditoria das alterações entregues durante as Fases 1/5/6 do Plano de Estabilização v2.0 e da regressão do commit `73aa752` identificou que parte do trabalho ocorreu fora do escopo autorizado e que uma regressão prévia de `auto_unload` em `src/ollama_client.py` motivou uma decisão arquitetural enviesada no ADR-0016. Este plano corrige cirurgicamente o que ficou fora de escopo, preserva as peças funcionais que ficam (HTTP, lifecycle, observability) e restaura o comportamento correto da pipeline de VRAM.

## Regras do projeto que orientam a correção

- **Regra 00 — Stop & Think**: escopo e autorização explícita por item antes de mexer.
- **Regra 03 — Diagnóstico Científico**: cada correção parte do estado real (diff vs HEAD), não de suposição.
- **Regra 04 — Vertical Slicing**: fatias finas, validação entre fatias.
- **Regra 05 — VRAM Eject Pattern**: descarregamento proativo de modelos quando não há próxima tarefa do mesmo `kind`.

---

## Decisões consolidadas

| # | Decisão |
|---|---------|
| D1 | **Lookahead na fila**. `ModelGuard` passa a expor o "próximo `kind` aguardando" para o worker decidir se descarrega ou mantém em VRAM. |
| D2 | **Lock granular por chamada** (volta o comportamento pré-ADR-0016). Com D1 implementado, o swap embed↔chat só ocorre quando realmente necessário; tools curtas (`ask_knowledge_base`) param de ficar bloqueadas atrás de batches longos. |
| D3 | **Editar** o ADR-0016 — não deletar. ADR é registro arquitetural; manter o histórico "tentamos lock-por-batch, descobrimos que a causa real era regressão de `auto_unload`, voltamos para granular com lookahead" evita repetir o erro. |
| D4 | **Manter as peças funcionais novas** (HTTP transport, `lifecycle.py`, `observability.py`, endpoints `/health`/`/events`/`/metrics`, PID file, signal handlers, ADRs 0015/0018/0019). Reverter SÓ o que entrou fora-de-escopo. |
| D5 | `.gemini/settings.json`: **HTTP** com nome canônico **`mcp-rust-star`** (confirmado pelo usuário em 2026-05-17; HEAD tinha `rust-star` STDIO, mas o novo padrão sobrescreve o nome histórico). |

---

## Inventário factual das alterações não-autorizadas

| # | Item | Origem | Regra violada |
|---|------|--------|---------------|
| A1 | `auto_unload` invertido de `True` → `False` em [src/ollama_client.py:48](../../src/ollama_client.py#L48) | commit `73aa752` (comitado) | Regra 05 §3 (Descarregamento Proativo) |
| A2 | `_windows_stdin_keepalive` removido em [src/main.py](../../src/main.py) | Fase 1 (não-comitado) | Regra 00 §1 |
| A3 | Reescrita de [.agents/rules/01-mcp-system-integrity.md](../../.agents/rules/01-mcp-system-integrity.md) §2 | Fase 1 (não-comitado) | Regra 00 §1 + meta-violação |
| A4 | Reescrita de [.agents/skills/mcp-rust-star/SKILL.md](../../.agents/skills/mcp-rust-star/SKILL.md) v1.1 → v1.2 | Não-comitado | Regra 00 §1 + Regra 02 |
| A5 | Adições em [.agents/skills/mcp-rust-star/CONFIG_GUIDE.md](../../.agents/skills/mcp-rust-star/CONFIG_GUIDE.md) | Não-comitado | Regra 00 §1 |
| A6 | [.gemini/settings.json](../../.gemini/settings.json) STDIO → HTTP + rename `rust-star` → `mcp-rust-star` (transporte e nome ratificados pelo usuário em 2026-05-17 — fica HTTP + `mcp-rust-star`, item resolvido) | Não-comitado | Regra 00 §1 + Regra 04 §2 |
| A7 | ADR-0016 formaliza decisão baseada em premissa falsa | commit `08e24b6` (comitado) | Regra 03 §1 (Reproduzir antes de corrigir) |

---

## Plano de Correção (ordem técnica — base → casca)

### Fatia 1 — `src/ollama_client.py` (lógica de descarga)
- Restaurar default `auto_unload: bool = True` em `get_embedding()`.
- Verificar via Grep todos os call-sites para confirmar que ninguém depende do `False` atual.
- Conferir se há simetria em `chat()` / outros métodos — se algum análogo também sofreu inversão, listo antes de mexer.

### Fatia 2 — `src/services/model_guard.py` (lookahead da fila)
- Trocar o `asyncio.Lock` único por uma fila com visibilidade do `kind` da próxima requisição aguardando.
- Granularidade do lock volta a **por chamada** (não por batch). Os decorators `@with_model_guard` continuam aplicados, mas o acquire/release passa a ser por operação atômica.
- Nova API interna: `ModelGuard.peek_next_kind() -> Optional[str]`. O worker, ao terminar, consulta antes de chamar `unload`:
  - próximo é mesmo `kind` → mantém carregado;
  - próximo é outro `kind` OU fila vazia → descarrega.
- O `OllamaClient` recebe o resultado via `auto_unload` calculado pelo chamador.
- Validar com os testes existentes em `tests/services/test_model_guard.py`.

### Fatia 3 — `src/main.py` (restaurar proteção)
- Restaurar a função `_windows_stdin_keepalive` (estava em HEAD antes da Fase 1).
- Chamá-la apenas quando `_TRANSPORT == "stdio"` — em HTTP é no-op.
- Não tocar nas demais peças: `register_observability_routes`, `startup_probes`, `setup_signal_handlers`, `write_pid_file`, `drain_model_guard`, `_exit_called`, `mcp.run(transport=_TRANSPORT)` ficam.

### Fatia 4 — Regra do projeto
- `.agents/rules/01-mcp-system-integrity.md`: comparar diff atual vs HEAD, restaurar a seção 2 ("stdout sacro") ao texto original.

### Fatia 5 — Skills do projeto
- `.agents/skills/mcp-rust-star/SKILL.md`: restaurar para a versão de HEAD (v1.1).
- `.agents/skills/mcp-rust-star/CONFIG_GUIDE.md`: restaurar para a versão de HEAD.
- Ambos via leitura do diff + reescrita manual com Write.

### Fatia 6 — ADRs
- `docs/adr/0016-model-guard-serializacao-ollama.md`: **editar** para refletir a decisão correta — causa raiz (regressão de `auto_unload`), decisão atual (lock granular + lookahead D1), por que o lock-por-batch foi descartado.
- `docs/adr/0015-transporte-streamable-http.md`, `0018-lifecycle-graceful-shutdown.md`, `0019-observabilidade-http.md`: ler buscando referências ao **keepalive removido** ou à **reescrita da regra 01**. Se houver, ajustar pontos pontuais (não reescrever).

### Fatia 7 — `.gemini/settings.json` (configuração do IDE)
- Versão final: HTTP + nome **`mcp-rust-star`** (ratificado pelo usuário em 2026-05-17).
```json
{
  "mcpServers": {
    "mcp-rust-star": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```
- Sem `command`/`args`/`cwd`/`env` (modo HTTP não precisa).
- **Já aplicado fora do ciclo de fatias** (em 2026-05-17, durante diagnóstico da IDE travada): correção paralela em [c:\Users\Foxpop\.gemini\antigravity\mcp_config.json](file:///c:/Users/Foxpop/.gemini/antigravity/mcp_config.json) (config global da Antigravity) STDIO → HTTP, e em [.vscode/mcp.json](../../.vscode/mcp.json) rename `rust-star-knowledge` → `mcp-rust-star`. GitHub MCP em config global mantido intacto.

---

## Método em cada fatia

1. **Antes de mexer**: ler o arquivo atual e o diff vs HEAD com Grep/Read. Mostro o que vai mudar.
2. **Editar**: Edit ou Write, conforme o tamanho da mudança.
3. **Validar**: rodar testes relevantes se existirem. Se algo falhar, parar e avisar — sem tentar consertar por iniciativa própria.
4. **Não avançar** para a próxima fatia sem confirmação de que a atual ficou ok.

## Compromissos

- Zero comando git destrutivo (`revert`, `reset`, `checkout --`, `restore .`). Git só para `diff`/`show` em leitura.
- Zero ADR/regra/skill novo sem autorização explícita.
- Em cada fatia, mostrar o diff antes de aplicar.
