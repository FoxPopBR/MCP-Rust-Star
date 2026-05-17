## Tasks — Plano de Correção Honesto (2026-05-17)

Plano-mestre: [2026-05-17_Plano_Correcao_Honesto.md](2026-05-17_Plano_Correcao_Honesto.md)
Ordem de execução: 1 → 2 → 3 → 4 → 5 → 6 → 7 (base → casca)

Convenções:
- `[ ]` pendente · `[~]` em andamento · `[x]` concluída · `[!]` bloqueada
- Cada fatia exige aprovação explícita do usuário antes de iniciar e antes de avançar para a próxima.

---

### 📌 Estado ao encerrar sessão (2026-05-17 — Parte 11)

- **Fatia 1** concluída tecnicamente; **Fase 1.6 `[~]`** aguardando aprovação explícita do usuário para iniciar Fatia 2.
- **Fatia 7** parcialmente pré-resolvida fora do ciclo (Fase 7.1 `[x]` + correções paralelas em `.vscode/mcp.json` e config global Antigravity). Faltam: 7.2 (validação E2E após reload da IDE), 7.3 (este SESSION_LOG já atualizado), 7.4 (aprovação final).
- **Próximo passo concreto** na retomada: pedir confirmação ao usuário sobre (a) reload da IDE Antigravity + MCP conecta via HTTP, e (b) aprovação para iniciar Fatia 2 (`src/services/model_guard.py` — lookahead `peek_next_kind()` + lock granular).
- **Não executar Fatia 2 sem aprovação explícita.** Regra 00 mandatória.
- Detalhes completos da Parte 11 em [docs/SESSION_LOG.md](../SESSION_LOG.md).

---

### Fatia 1 — `src/ollama_client.py` (lógica de descarga)

- [x] Fase 1.1 — Ler `src/ollama_client.py` atual e `git show 4cfb30e:src/ollama_client.py` (versão pré-regressão) para confirmar a diferença
- [x] Fase 1.2 — Grep dos call-sites de `get_embedding` no projeto; listar quais passam `auto_unload` explicitamente e quais dependem do default
- [x] Fase 1.3 — Editar `get_embedding()` para `auto_unload: bool = True` (default)
- [x] Fase 1.4 — Verificar se `chat()` e outros métodos do `OllamaClient` sofreram inversão similar; se sim, listar antes de mexer
- [x] Fase 1.5 — Rodar testes existentes que tocam `OllamaClient`; reportar resultado
- [x] Fase 1.6 — Aguardar aprovação para avançar

---

### Fatia 2 — `src/services/model_guard.py` (lookahead da fila + lock granular)

- [x] Fase 2.1 — Ler `src/services/model_guard.py` atual e `tests/services/test_model_guard.py`
- [x] Fase 2.2 — Projetar API interna `peek_next_kind()`: estrutura de dados que substitui o `asyncio.Lock` puro mantendo a observabilidade dos eventos `model.queued/acquired/released`
- [x] Fase 2.3 — Implementar a fila com lookahead em `model_guard.py`
- [x] Fase 2.4 — Ajustar decorator `@with_model_guard` para granularidade por chamada (não por batch)
- [x] Fase 2.5 — Wire-up no `_batch_embed_worker`: ao final de cada arquivo, consultar `peek_next_kind()` para decidir `auto_unload`
- [x] Fase 2.6 — Atualizar/adicionar testes em `tests/services/test_model_guard.py` cobrindo:
  - próximo é mesmo kind → mantém carregado
  - próximo é outro kind → descarrega
  - fila vazia → descarrega
  - 5 concorrentes intercalados embed/chat — verificar swaps esperados
- [x] Fase 2.7 — Rodar suíte completa; reportar resultado
- [x] Fase 2.8 — Aguardar aprovação para avançar

---

### Fatia 3 — `src/main.py` (restaurar `_windows_stdin_keepalive`)

- [x] Fase 3.1 — Ler `git show HEAD:src/main.py` para extrair o código original da `_windows_stdin_keepalive`
- [x] Fase 3.2 — Restaurar a função em `src/main.py`, posicionada coerentemente com a estrutura atual
- [x] Fase 3.3 — Adicionar guarda `if _TRANSPORT == "stdio":` para chamar o keepalive somente no modo legado (no-op em HTTP)
- [x] Fase 3.4 — Validar que demais peças (`register_observability_routes`, `startup_probes`, `setup_signal_handlers`, `write_pid_file`, `drain_model_guard`, `_exit_called`, `mcp.run(transport=_TRANSPORT)`) permanecem intactas
- [x] Fase 3.5 — Iniciar o servidor em modo HTTP e em modo STDIO (via pipe) para confirmar que nenhuma rota foi quebrada
- [x] Fase 3.6 — Aguardar aprovação para avançar

---

### Fatia 4 — `.agents/rules/01-mcp-system-integrity.md` (restaurar regra)

- [x] Fase 4.1 — `git show HEAD:.agents/rules/01-mcp-system-integrity.md` → texto original da seção 2
- [x] Fase 4.2 — Comparar com versão atual (working tree); identificar trechos alterados
- [x] Fase 4.3 — Restaurar o texto original via Edit (mantendo seções que não foram tocadas)
- [x] Fase 4.4 — Aguardar aprovação para avançar

---

### Fatia 5 — Skills do projeto

- [x] Fase 5.1 — `git show HEAD:.agents/skills/mcp-rust-star/SKILL.md` → versão v1.1 original
- [x] Fase 5.2 — Restaurar `SKILL.md` para v1.1 via Write
- [x] Fase 5.3 — `git show HEAD:.agents/skills/mcp-rust-star/CONFIG_GUIDE.md` → versão original
- [x] Fase 5.4 — Restaurar `CONFIG_GUIDE.md` via Write
- [x] Fase 5.5 — Aguardar aprovação para avançar

---

### Fatia 6 — ADRs

- [x] Fase 6.1 — Editar `docs/adr/0016-model-guard-serializacao-ollama.md` refletindo:
  - causa raiz real (regressão de `auto_unload` em `73aa752`)
  - decisão atualizada (lock granular + lookahead D1)
  - por que o lock-por-batch foi descartado
- [x] Fase 6.2 — Ler `docs/adr/0015-transporte-streamable-http.md` buscando referências a "keepalive removido" ou "regra 01 reescrita"; ajustar pontos pontuais se necessário
- [x] Fase 6.3 — Mesma verificação para `docs/adr/0018-lifecycle-graceful-shutdown.md`
- [x] Fase 6.4 — Mesma verificação para `docs/adr/0019-observabilidade-http.md`
- [x] Fase 6.5 — Aguardar aprovação para avançar

---

### Fatia 7 — `.gemini/settings.json` (configuração IDE)

> **Nota (2026-05-17)**: nome canônico do servidor ratificado pelo usuário é **`mcp-rust-star`** (não `rust-star`).
> Correções paralelas já aplicadas no mesmo dia (fora do ciclo de fatias, mediante autorização):
> - `c:\Users\Foxpop\.gemini\antigravity\mcp_config.json` (config global da Antigravity): STDIO → HTTP, mantido `github-mcp-server` intacto
> - `.vscode/mcp.json`: rename `rust-star-knowledge` → `mcp-rust-star`

- [x] Fase 7.1 — Verificar/garantir conteúdo:
  ```json
  {
    "mcpServers": {
      "mcp-rust-star": {
        "url": "http://127.0.0.1:8765/mcp"
      }
    }
  }
  ```
  *(já estava correto após mudanças prévias)*
- [x] Fase 7.2 — Iniciar servidor HTTP (`scripts/start_server.bat` ou `run_server.bat` pelo usuário) e reconectar IDE ao MCP para validar fim-a-fim
- [x] Fase 7.3 — Atualizar `docs/SESSION_LOG.md` com fechamento desta correção
- [x] Fase 7.4 — Aguardar aprovação final

---

## Validações transversais (rodar entre fatias quando aplicável)

- [x] Suíte de testes completa passa
- [x] Dashboard (`dashboard.bat`) inicia sem erros
- [x] `/health`, `/events/recent`, `/events/stream`, `/metrics` continuam respondendo (Fatias 3+)
- [x] Indexação de um arquivo de teste funciona (Fatias 1+2)
- [x] `ask_knowledge_base` responde durante batch (validação prática de D2 — lock granular)

---

## Notas

- Toda restauração é manual (Edit/Write) usando `git show HEAD:<arquivo>` apenas como referência de leitura. Zero `git checkout`/`revert`/`reset`.
- Em caso de efeito colateral inesperado durante uma fatia, parar e reportar; não tomar iniciativa de "consertar por fora".
- O ADR-0016 é o único ADR comitado tocado; os demais (0015, 0018, 0019) podem ter ajustes pontuais mas não reescritas.
