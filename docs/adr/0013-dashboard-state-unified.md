# ADR-0013: Pipeline de Telemetria Unificada (`dashboard_state.json`)

## Status
Aplicado (16/05/2026).

## Contexto

O dashboard de monitoramento dependia de **três fontes distintas** de telemetria:
- `data/current_indexing.json` — estado do `RAGService` (arquivo atual, stats)
- `data/embed_batch.json` — fila batch (`_persist_batch_state()` em main.py)
- `logs/mcp_error.log` — tail físico lido pelo `DataFetcher`

Esse desenho produziu três problemas crônicos:
1. **Race conditions** — escritas concorrentes nos JSONs corrompiam frames (cura via `os.replace`, mas só em alguns pontos).
2. **Contenção de file lock** no `mcp_error.log` (15 MB) entre servidor escrevendo e dashboard tailando — causa documentada de freezes (ver ADR 0012 e `feedback_dashboard_principles.md`).
3. **Schema implícito divergente** entre escritores — painel `FILA DE PROJETOS` quebrou quando `_persist_batch_state` deixou de gravar `total_projects` mas o painel ainda esperava o campo.

## Decisão

Centralizar **toda telemetria** num único arquivo `data/dashboard_state.json`, escrito por um **único componente** do servidor: `TelemetryWriter` (em `src/services/telemetry_writer.py`).

### Schema (versão 1)

```jsonc
{
  "version": 1,
  "ts": "2026-05-16T14:32:11",
  "server": {
    "alive": true,
    "last_query": { ... } | null
  },
  "indexing": {
    "running": false, "canceled": false,
    "current_project": "...", "current_file": "...", "current_folder": "...",
    "current_fragment": 0, "total_fragments": 0, "total_expected": 0,
    "stats": { "new": 0, "cached": 0, "skipped": 0, "errors": 0 },
    "stats_by_ext": { ".rs": 12, ".lua": 4 },
    "error_files": [],
    "queue": [], "completed": [],
    "started_at": null, "finished_at": null,
    "total_projects": 0
  },
  "batch": {
    "completed": [],
    "results": {}
  },
  "inventory": {
    "Rust Star": { "total": 1234, "extensions": { ".rs": 800, ".toml": 5 } }
  },
  "log_tail": [ "linha 1", "linha 2", ... ]   // últimas 28 linhas
}
```

### Componentes

- **`TelemetryWriter`** — escritor único:
  - `snapshot(embed_state, rag_state, batch_progress, server_extra)` monta o payload acima.
  - `persist(payload)` aplica throttle de 250ms + escrita atômica via `.tmp + os.replace`.
  - `flush(payload)` força escrita ignorando throttle (usado em shutdown / fim de batch).
  - `write(...)` = `snapshot(...)` + `persist(...)`.

- **`InventoryProvider`** — cache TTL (60s) sobre `db.list_sources()`:
  - Evita query no Postgres a cada frame.
  - `invalidate()` chamado após cada batch para refrescar imediatamente.

- **`_publish_telemetry()`** (em `src/main.py:55-64`) — closure que chama `TelemetryWriter.write` com o estado consolidado. Plugada em:
  - `rag._on_state_change = _publish_telemetry` — toda mutação do `RAGService.state`.
  - `_embed_log()` — após cada linha de log capturada.
  - `_walk_and_index_sync()` — após cada arquivo processado.
  - `_batch_embed_worker` — após cada projeto + `flush()` no `finally`.
  - Após cada `search_knowledge` (popula `server_extra["last_query"]`).

- **`DataFetcher`** (em `dashboard/fetcher.py`) — agora com **assinatura simplificada**: `__init__(ollama_url, state_file)`. Lê apenas `dashboard_state.json` e sintetiza `state_view` + `batch_view` (achatamento que preserva a API dos painéis existentes sem editá-los).

### Removidos

- `data/current_indexing.json` — substituído por `dashboard_state.json::indexing`.
- `data/embed_batch.json` — substituído por `dashboard_state.json::indexing` (queue/completed) + `dashboard_state.json::batch`.
- Tail físico de `logs/mcp_error.log` no `DataFetcher` — substituído por `dashboard_state.json::log_tail` (alimentado em `_embed_log`).
- `dashboard.py` (raiz, legado) — removido; ponto de entrada agora é `dashboard/__main__.py` invocado por `dashboard.bat`.
- `tools/diag_live_freeze.py` — promovido a `tests/dashboard/test_live_repaints.py` (ver ADR 0012).

## Consequências

**Positivas:**
- **Um schema, um escritor, uma fonte de verdade.** Inconsistências entre painéis ficam impossíveis por construção.
- **Throttle no servidor**, não no dashboard. O servidor define a cadência (250ms) — o dashboard apenas le.
- **Atomicidade garantida** em todas as escritas (`os.replace`).
- **Zero contenção** com `mcp_error.log`: o tail vive no JSON, capturado em memória pelo handler de log do `_embed_log`.
- **Princípio "dashboard não atrapalha o servidor" reforçado**: o dashboard agora faz apenas um `read+json.load` a cada 250ms, sem tocar em arquivos do servidor.
- **Painel `FILA DE PROJETOS` volta a funcionar**: re-empacotamento em `batch_view` no `DataFetcher` preserva contrato visual sem novos campos no schema.

**Negativas:**
- Schema versionado obriga atenção em mudanças (bumpear `SCHEMA_VERSION` se quebrar consumers).
- `_publish_telemetry` precisa ser chamado em todo ponto de mutação relevante. Mitigação: callback `rag._on_state_change` cobre 80% dos casos automaticamente.

## Regression test

`tests/dashboard/test_live_repaints.py` (ADR 0012) garante o repaint do Rich Live. Não há ainda teste do schema do `dashboard_state.json` — candidato natural para um próximo ciclo (validação do JSON contra um esquema fixo).

## Referências

- `src/services/telemetry_writer.py` — implementação completa.
- `src/main.py:45-64` — wire-up do `TelemetryWriter` no servidor.
- `dashboard/fetcher.py` — consumidor único do `dashboard_state.json`.
- `docs/adr/0012-dashboard-live-freeze-postmortem.md` — fix do freeze do Rich Live (complementar).
