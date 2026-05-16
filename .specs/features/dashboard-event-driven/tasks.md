# Tasks: Dashboard Standby + Event-Driven

- [ ] **Fase 1: Backend (Telemetry & Activity)**
    - [ ] `[ ]` Finalizar `TelemetryWriter.snapshot` para incluir o campo `activity`.
    - [ ] `[ ]` Implementar método `heartbeat()` no `TelemetryWriter`.
    - [ ] `[ ]` Envolver ferramentas MCP em `main.py` com o context manager `activity()`.
    - [ ] `[ ]` Iniciar thread de heartbeat no startup do `main.py`.

- [ ] **Fase 2: Lógica de Estado**
    - [ ] `[ ]` Criar `dashboard/state_decider.py` com a lógica de transição 🟢/🟡/🔴/⚫.
    - [ ] `[ ]` Criar testes unitários em `tests/dashboard/test_state_decider.py`.

- [ ] **Fase 3: Dashboard Event-Driven**
    - [ ] `[ ]` Refatorar `DataFetcher` para usar `watchfiles` em vez de polling fixo.
    - [ ] `[ ]` Atualizar `DashboardApp` para exibir o LED e texto de status no Header.
    - [ ] `[ ]` Tornar o Spinner condicional (apenas em estado `active`).

- [ ] **Fase 4: Documentação e Finalização**
    - [ ] `[ ]` Criar `docs/adr/0014-dashboard-event-driven-standby.md`.
    - [ ] `[ ]` Atualizar `SESSION_LOG.md`.
