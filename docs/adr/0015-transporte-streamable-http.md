# ADR-0015: Transporte Streamable-HTTP para o Servidor MCP

O servidor MCP Rust Star operava exclusivamente via STDIO, vinculando o processo servidor ao processo cliente em uma relação 1:1. Isso impede conexões simultâneas de múltiplos clientes (IDE + terminal + dashboard HTTP) e exige o workaround `_windows_stdin_keepalive` para contornar deadlock do ProactorEventLoop do Windows.

## Contexto

O modo STDIO tem três limitações concretas:

1. **Conexão 1:1**: apenas um cliente por vez pode usar o servidor. Um segundo IDE ou cliente Python tentando conectar ao mesmo servidor não consegue — precisaria de uma segunda instância com estado independente.
2. **Workaround de plataforma**: `_windows_stdin_keepalive` existe apenas para evitar que o `ProactorEventLoop` do Windows bloqueie o stdin quando não há leitura ativa. Lógica de infraestrutura que não deveria existir no nível de aplicação.
3. **Bloqueio do Fase 6**: o endpoint `/events/stream` (SSE) e `/health` (Fase 6) requerem um servidor HTTP escutando numa porta — incompatível com STDIO puro.

## Decisão

Migrar o transporte para `streamable-http` usando a API nativa do FastMCP 1.27+:

```python
mcp.run(transport="streamable-http")
```

O servidor escuta em `127.0.0.1:8765` (configurável via `data/defaults.json`). O endpoint MCP fica em `http://127.0.0.1:8765/mcp`. Clientes configuram uma URL em vez de um comando de processo.

Consequências diretas:
- `_windows_stdin_keepalive` removido — o bloqueio de stdin não ocorre em transporte HTTP.
- Regra 01 §2 ("stdout sacro") fica restrita ao modo STDIO legado; no modo HTTP o stdout não é o canal MCP.
- `data/defaults.json` passa a ter seção `server` com `transport`, `host` e `port`.

## Configuração de cliente

**Antes (STDIO):**
```json
{
  "command": "c:/Phantasy/MCP Rust Star/.venv/Scripts/python.exe",
  "args": ["-m", "src.main"],
  "cwd": "c:/Phantasy/MCP Rust Star"
}
```

**Depois (streamable-http):**
```json
{
  "url": "http://127.0.0.1:8765/mcp"
}
```

## Alternativas consideradas

- **SSE transport**: suportado pelo FastMCP, mas deprecated na spec MCP 2025-03-26. Streamable-HTTP é o sucessor designado.
- **Manter STDIO**: não resolve a limitação multi-cliente nem desbloquia a Fase 6. `_windows_stdin_keepalive` continuaria existindo como débito técnico.
- **FastAPI separado ao lado do MCP**: adiciona complexidade de dois processos sem ganho — `run_streamable_http_async` já serve o MCP via uvicorn, e rotas adicionais podem ser montadas na mesma app ASGI (Fase 6).

## Auto-detecção de transporte e prioridade

O servidor implementa uma cadeia de prioridade para determinar o transporte em runtime, sem exigir que o operador altere configurações manuais para o caso de uso mais comum (IDE via stdin pipe):

```
1. --transport <valor>   →  explícito via CLI (maior prioridade)
2. sys.stdin.isatty() == False  →  stdin é pipe (IDE invocou via JSON config) → STDIO automático
3. data/defaults.json ["server"]["transport"]  →  valor padrão ("streamable-http")
```

**Fluxo IDE (STDIO automático):**
Quando um IDE como Cursor ou VS Code invoca o servidor via configuração JSON (`"command"` + `"args"`), ele conecta stdin/stdout do processo a pipes internos. Nesse contexto, `sys.stdin.isatty()` retorna `False` — o servidor detecta que foi chamado via pipe e seleciona STDIO automaticamente, sem necessidade de `--transport stdio` no JSON de configuração.

```json
{
  "command": "c:/Phantasy/MCP Rust Star/.venv/Scripts/python.exe",
  "args": ["-m", "src.main"],
  "cwd": "c:/Phantasy/MCP Rust Star"
}
```

**Proteção STDIO vs HTTP simultâneo:**
`startup_probes()` (ADR-0018) verifica a porta configurada antes de subir. Em modo STDIO, se a porta estiver ocupada (servidor HTTP ativo), o processo encerra com `sys.exit(1)` e mensagem `CRITICAL` — rodar STDIO com HTTP ativo corromperia o canal stdout do MCP.

## Consequências

- Múltiplos clientes podem conectar simultaneamente ao mesmo servidor (modo HTTP).
- `_windows_stdin_keepalive` removido de `src/main.py` — código de infraestrutura eliminado.
- Fase 6 (`/health`, `/events/stream`) pode ser implementada montando rotas Starlette na mesma app ASGI exposta pelo FastMCP.
- Latência de transporte aumenta ligeiramente (HTTP vs pipe), irrelevante para ferramentas RAG com operações na escala de segundos.
- Clientes HTTP precisam ser reconfigurados para URL. O `data/defaults.json` documenta host/porta canônicas.
- IDEs com configuração `"command"` continuam funcionando sem alteração — STDIO é selecionado automaticamente via detecção de pipe.
