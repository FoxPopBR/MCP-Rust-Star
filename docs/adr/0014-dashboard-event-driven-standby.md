# ADR-0014: Dashboard Event-Driven + Standby Mode

## Contexto
O dashboard anterior utilizava polling fixo de 250ms para ler o estado do servidor do disco. Isso resultava em:
1.  Uso desnecessário de CPU e I/O mesmo quando o servidor estava ocioso.
2.  Dificuldade em distinguir entre um servidor ocioso e um servidor travado (crash).
3.  Falta de feedback visual sobre o nível de atividade real do servidor.

## Decisões

### 1. Arquitetura Orientada a Eventos
O dashboard agora utiliza a biblioteca `watchfiles` para reagir a mudanças no arquivo `dashboard_state.json`. 
-   O fetcher entra em modo bloqueante (com timeout de segurança) aguardando o evento de escrita do SO.
-   A frequência de atualização do dashboard passa a ser ditada pelo servidor (push-like behavior via disco).

### 2. Sistema de Refcount de Atividade
O `TelemetryWriter` no servidor implementa um contador de referência (`activity_count`).
-   Qualquer ferramenta MCP ou worker de background incrementa o contador ao iniciar e decrementa ao finalizar.
-   Isso permite que o servidor publique seu estado como `active`, `idle` ou `error`.

### 3. Heartbeat de 10 Segundos
Uma thread dedicada no servidor publica a telemetria a cada `HEARTBEAT_SECONDS = 10s`, mesmo sem atividade.
-   Permite que o dashboard detecte "Server Offline" se o timestamp for muito antigo (`STALE_THRESHOLD_SECONDS = 25s`, ou seja, > 2× heartbeat — tolera atraso de uma batida sem flicker).
-   Mantém o dashboard "vivo" sem polling agressivo do lado UI.

### 4. Feedback Visual (LED + Texto no Header)
O header exibe LED **e** rótulo descritivo (não só cor — acessibilidade e legibilidade em terminais sem cor):
-   🟢 **Servidor Ativo** (`#22c55e`) — processando ferramenta ou worker.
-   🟡 **Servidor em Standby** (`#eab308`) — vivo, fresco, ocioso.
-   🔴 **Erro no Servidor** (`#ef4444`) — última tool falhou; auto-limpa na próxima execução bem-sucedida.
-   ⚫ **Servidor Offline** (`#6b7280`) — sem snapshot, `alive=false`, ou `ts` stale.

### 5. Spinner = Fetching, NÃO Server Activity
**Decisão revisada**: o spinner gira *apenas* enquanto o dashboard está esperando dados aparecerem (`fetcher.is_fetching` ou `not fetcher.ready`). Quando o servidor está `active` e estável, o LED verde + rótulo no header já comunicam — animar spinner ali confunde "trabalhando" com "carregando" e polui a tela.

O `state_decider` é puramente um classificador semântico (status, label, color); a decisão de mostrar spinner pertence à UI e usa `fetcher.is_fetching` como fonte.

### 6. Prioridade de Estados
Ordem absoluta no decisor: `offline > error > active > standby`. Sem heartbeat fresco, qualquer outro campo é informação obsoleta — não importa o que o JSON dizia.

## Implementação

| Arquivo | Mudança |
|---|---|
| `src/services/telemetry_writer.py` | Schema v2; refcount `activity_count`; `heartbeat_loop()`; `server.activity` ∈ {idle,active,error} |
| `src/main.py` | Decorator `mcp_tool_with_logging` envolve em `_telemetry.activity()`; auto-clear de error em sucesso; thread daemon `heartbeat_loop` |
| `dashboard/state_decider.py` | Função pura `decide_state(snapshot) → {status,label,color}` |
| `dashboard/fetcher.py` | Loop event-driven via `watchfiles.watch()` com `stop_event`; expõe `is_fetching` |
| `dashboard/app.py` | LED + texto no header; spinner condicional via `fetcher.is_fetching` |
| `tests/dashboard/test_state_decider.py` | Matriz table-driven (alive × activity × frescor) |

## Consequências
-   I/O do dashboard cai de 4 leituras/s para ~1 leitura cada 10s (steady-state idle) + leituras event-driven em mudança.
-   Crash do servidor detectado em ≤ 25s sem polling pelo dashboard.
-   Erros não ficam "stuck" — limpam-se naturalmente na próxima tool OK.
-   Servidor é única fonte de verdade do `activity`; dashboard é puramente reativo.
