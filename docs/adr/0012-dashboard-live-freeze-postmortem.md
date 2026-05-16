# ADR-0012: Post-Mortem — Dashboard "carrega imagem inicial e trava"

## Status
Aplicado (16/05/2026). Fix A em produção em `dashboard/app.py:594` (`auto_refresh=True, refresh_per_second=25`). Regression test promovido para `tests/dashboard/test_live_repaints.py`.

## Sintoma reportado

O dashboard exibe o frame inicial e nunca mais atualiza. Relógio do header, contadores de stats, painel de progresso, fila de logs — nada muda visualmente, mesmo com o servidor ativo escrevendo `data/current_indexing.json` e `logs/mcp_error.log`.

Reincidência: terceira vez no ciclo 2026-05-15/16 (ver `feedback_dashboard_principles.md`). As duas primeiras foram causa diferente (file-lock contention com `mcp_error.log`). Esta é causa nova.

## Diagnóstico (skill `diagnose`)

### Phase 1 — Feedback loop
Harness descartável `tools/diag_live_freeze.py` reproduz o sintoma em isolamento total:
- Instancia `rich.live.Live` com a mesma configuração do dashboard
- Captura bytes emitidos ao "stdout" (na verdade `io.StringIO`) em 3 frames consecutivos
- Pass/fail determinístico em ~2 segundos
- Comparação de 3 cenários numa única corrida: config atual, fix-A, fix-B

### Phase 2 — Repro
RUN A (config atual): `(0, 0, 0)` bytes emitidos entre frames. **Bug 100% reproduzível.**

### Phase 3 — Hipóteses (resumo, detalhes na conversa)
- **H1 (Rich Live não repinta sem refresh)** — CONFIRMADA pelo harness
- H2 (KeyError em painel inventário) — falsificada (harness não usa painel inventário)
- H3 (DataFetcher segura lock) — falsificada (harness não usa DataFetcher)
- H4 (contenção com `mcp_error.log`) — irrelevante para este sintoma
- H5 (`time.sleep` capturado por OS scheduling) — falsificada

### Phase 4 — Instrumentação
Harness substitui logs ad-hoc: sinal binário objetivo, sem ambiguidade.

## Causa raiz

`dashboard/app.py:591`:
```python
with Live(initial, screen=True, auto_refresh=False) as live:
    while True:
        live.update(app.update())          # <- NÃO repinta
        time.sleep(0.25)
```

`rich.live.Live` separa "trocar o renderable" (`.update()`) de "emitir bytes ao stdout" (`.refresh()`). Com `auto_refresh=False` e sem `live.refresh()` (nem `update(..., refresh=True)`), o alternate-screen recebe apenas o frame emitido pelo `__enter__` do context manager. Todos os `update()` subsequentes mutam estado interno do Rich mas não fazem repaint.

Documentação Rich: `auto_refresh=True` é o default precisamente porque o uso típico assume repaint automático em background via thread daemon `_RefreshThread`. Foi `auto_refresh=False` desligado provavelmente para "evitar contenção" — uma otimização sem efeito real que quebrou o caso de uso.

## Decisão (Fix A aplicado)

**Fix A — aplicado em `dashboard/app.py:594`:**
```python
with Live(initial, screen=True, auto_refresh=True, refresh_per_second=25, console=console) as live:
    while not stop_event.is_set():
        live.update(app.update())
        stop_event.wait(0.25)
```

Rationale:
- Rich gerencia o repaint em thread daemon a 4 Hz independente do polling
- Resolve a queixa colateral "relógio só anda no ritmo do polling"
- Mantém custo de CPU baixo (alternate-screen + 4 fps + diff interno do Rich)
- `stop_event.wait()` em vez de `time.sleep()` permite shutdown limpo

**Fix B — alternativa:** manter `auto_refresh=False` e adicionar `live.refresh()` após cada `update`. Mais previsível, mais código, sem ganho real.

## Regression test

`tools/diag_live_freeze.py` vira `tests/dashboard/test_live_repaints.py` com assertions pytest. ~10 linhas de adaptação. Trava CI se alguém reintroduzir `auto_refresh=False` sem refresh manual.

## Consequências

- **Positivas:**
  - Dashboard volta a renderizar a 4 Hz autonomamente, mesmo se DataFetcher trava
  - Relógio, logs e stats atualizam sem depender de polling de JSON
  - Regression test impede reincidência
  - Princípio "dashboard não pode atrapalhar o servidor" preservado (sem novo IO)

- **Riscos:**
  - `_RefreshThread` do Rich é mais um daemon. Já temos 2 do DataFetcher → total 3. Aceitável.
  - Se o renderable produzido por `app.update()` levantar exceção, com `auto_refresh=True` o Rich pode reportar de forma diferente. Mantém o `try/except` envolvendo `live.update()`.

## O que teria prevenido isso

Regression test desde o início. O dashboard nunca teve teste de render — só de unidades isoladas. A skill `diagnose` Phase 6 pergunta "what would have prevented this bug?" — resposta: um teste headless que mediria bytes emitidos em N frames. Exatamente o `tools/diag_live_freeze.py`. Promovê-lo a teste permanente fecha o ciclo.

## Cleanup

Pós-aplicação do fix:
- [x] Migrar `tools/diag_live_freeze.py` para `tests/dashboard/test_live_repaints.py`
- [x] Deletar `tools/diag_live_freeze.py`
- [x] Atualizar memória `feedback_dashboard_principles.md` com a regra: "Rich `Live` no dashboard SEMPRE `auto_refresh=True` ou chamar `refresh()` explicitamente."
- [ ] Commit message cita H1 confirmada para o próximo debugger (pendente — feito no próximo commit do usuário)
