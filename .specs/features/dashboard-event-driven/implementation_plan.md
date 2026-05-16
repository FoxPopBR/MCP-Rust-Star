# Implementation Plan: Dashboard Standby + Event-Driven (ADR-0014)

## Objetivo
Eliminar o polling contínuo (250ms) do dashboard. O sistema passará a ser orientado a eventos:
1.  **Servidor**: Publica `dashboard_state.json` apenas quando há mudanças significativas ou via Heartbeat (10s).
2.  **Dashboard**: Utiliza `watchfiles` para reagir à escrita do arquivo, entrando em modo Standby (ociosidade de CPU/IO) quando não há atividade.

## Proposta Técnica

### 1. Servidor (Backend)
-   **TelemetryWriter (V2)**: 
    -   Implementar sistema de `refcount` para atividade (`idle` | `active` | `error`).
    -   Adicionar método `heartbeat()` que faz um `touch` no JSON a cada 10s para sinalizar que o servidor está vivo.
    -   Snapshot inclui o campo `activity`.
-   **Main.py**:
    -   Envolver ferramentas MCP e workers de background (`_batch_embed_worker`) no context manager `_telemetry.activity()`.
    -   Iniciar thread de heartbeat no startup.

### 2. Dashboard (Frontend/Fetcher)
-   **DataFetcher**:
    -   Substituir o loop de polling (`time.sleep`) por um `watchfiles.watch()` ou similar.
    -   Implementar fallback de timeout (ex: 5s) para garantir atualização caso o evento falhe.
-   **StateDecider (Novo)**:
    -   Função pura para determinar o estado visual (`active`, `standby`, `offline`, `error`) baseado no snapshot e timestamps.
-   **UI (Rich App)**:
    -   Header dinâmico: `🟢/🟡/🔴/⚫` + Texto descritivo.
    -   Spinner condicional: Ativo apenas durante `activity == "active"`.

## Mudanças Propostas

### [MODIFY] [telemetry_writer.py](file:///C:/Phantasy/MCP%20Rust%20Star/src/services/telemetry_writer.py)
- Finalizar a implementação do refcount e incluir `activity` no snapshot.

### [MODIFY] [main.py](file:///C:/Phantasy/MCP%20Rust%20Star/src/main.py)
- Envolver todas as ferramentas MCP com `@_telemetry.activity()`.
- Implementar e iniciar a thread de heartbeat.

### [NEW] [state_decider.py](file:///C:/Phantasy/MCP%20Rust%20Star/dashboard/state_decider.py)
- Lógica de decisão de estado visual.

### [MODIFY] [fetcher.py](file:///C:/Phantasy/MCP%20Rust%20Star/dashboard/fetcher.py)
- Migrar para `watchfiles`.

### [MODIFY] [app.py](file:///C:/Phantasy/MCP%20Rust%20Star/dashboard/app.py)
- Atualizar Header e lógica de renderização do spinner.

## Plano de Verificação

### Testes Automatizados
- `pytest tests/dashboard/test_state_decider.py` (Garantir transições de estado corretas).

### Verificação Manual
- Iniciar Dashboard e observar o LED mudar para 🟡 quando o servidor estiver ocioso.
- Rodar uma ferramenta MCP (ex: `list_projects`) e ver o LED mudar para 🟢 e o spinner aparecer.
- Derrubar o servidor e ver o LED mudar para ⚫ (após o timeout de heartbeat).
