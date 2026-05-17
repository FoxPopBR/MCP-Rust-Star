# AGENTS.md — MCP Rust Star Knowledge Server

> **Idioma**: Toda comunicação com o usuário, documentos gerados, planos e respostas devem ser em **português brasileiro (pt-BR)**.

## 🛑 REGRAS DE SEGURANÇA (CRÍTICO)

- **NUNCA ALTERE CÓDIGO SEM AUTORIZAÇÃO EXPLÍCITA**: Se a tarefa for análise, diagnóstico ou leitura, o agente deve **APENAS LER** e relatar. **PROIBIDO** escrever, editar ou rodar comandos destrutivos.
- **ANÁLISE ≠ ALTERAÇÃO**: Pedidos como "analise", "verifique", "diagnostique" ou "faça um relatório" **NÃO** dão permissão para modificar arquivos. O agente deve apenas ler e gerar relatórios em texto ou documentos novos.
- **RESPEITO AO TRABALHO HUMANO**: Nunca sobrescreva arquivos que possam estar sendo editados por outras pessoas. Se houver dúvida, **PERGUNTE** antes de tocar em qualquer arquivo `.py`, `.md` ou `.json`.
- **GIT É SAGRADO**: **NUNCA** rode `git checkout`, `git reset --hard`, `git clean` ou qualquer comando que sobrescreva arquivos locais sem ordem **DIRETA E EXPLÍCITA** do usuário. Isso destrói trabalho não commitado.
- **SEMPRE PEÇA PERMISSÃO**: Antes de criar, editar ou deletar qualquer arquivo no projeto, o agente deve listar o que pretende fazer e aguardar o "OK" do usuário.

## Comandos Rápidos

| Ação | Comando |
|---|---|
| Iniciar servidor MCP | `python -m src.main` (ou `run_server.bat` para pré-voo completo) |
| Iniciar dashboard | `python -m dashboard` (ou `dashboard.bat`) |
| Rodar testes | `pytest` (pytest + pytest-asyncio) |
| Rodar teste específico | `pytest tests/services/test_model_guard.py -k test_acquire` |
| Limpar DB + reindexar | `clear_and_embed.bat` |
| Subir Postgres | `docker compose up -d` |
| Verificar Ollama | `ollama list` — precisa de `qwen3-embedding:8b` e `qwen3.5:9b` |

## Arquitetura

```
src/main.py                     — Entrada MCP, definição de ferramentas (FastMCP)
src/services/rag_service.py     — Orquestração RAG (embed, busca, geração)
src/vector_store_postgres.py    — Persistência PostgreSQL + pgvector
src/ollama_client.py            — Cliente Ollama (embeddings, chat, vision)
src/config_manager.py           — Configurações: defaults de fábrica + overrides do usuário
tools/logger.py                 — CustomLogger → stderr apenas (stdout = JSON-RPC)
src/services/model_guard.py     — Serializa operações Ollama (uma por vez via asyncio.Lock)
src/services/event_bus.py       — Pub/sub in-process para eventos internos
src/services/telemetry_writer.py — Escreve estado do dashboard em data/dashboard_state.json
dashboard/                      — UI de monitoramento em tempo real (Textual TUI)
```

**Regra de camadas**: `main.py` (interface) → `rag_service.py` (serviço) → `vector_store_postgres.py` (persistência). Nunca pule camadas.

## Regras Críticas do Código

### Logging
- **NUNCA use `print()`** — stdout é reservado para o protocolo JSON-RPC do MCP. Todos os logs vão para `stderr` via `tools.logger`.
- Use `logger.info()`, `logger.error()`, etc. importando de `tools.logger`.
- Decore ferramentas MCP com `@mcp_tool_with_logging` (em `main.py`) para heartbeat + captura de erros.

### ModelGuard
- Todas as operações que tocam o Ollama são serializadas via `@with_model_guard(kind="embed"|"chat"|"vision")`.
- Não remova nem contorne este decorador — ele previne contenção de VRAM e thrashing de recarga de modelos.
- Kinds: `"embed"` (indexação), `"chat"` (RAG), `"vision"` (análise de imagem).

### Gestão de VRAM
- Após indexação em batch, os modelos são descarregados explicitamente: `rag.ollama.unload_models()`.
- Não adicione chamadas longas ao Ollama sem considerar o impacto na VRAM.

### Isolamento de Projetos
- Todo documento indexado é marcado com um `project_id`.
- `get_project_for_path()` associa arquivos a projetos por longest-prefix match nos caminhos registrados.
- Nunca permita vazamento de dados entre projetos a menos que explicitamente solicitado.

## Pipeline de Indexação

1. **Config**: `src/resources/defaults.json` define extensões permitidas/ignoradas e diretórios ignorados. Overrides do usuário persistem em `data/user_preferences.json`.
2. **Filtragem**: `config_manager.is_ignored()` verifica whitelist de extensões → blacklist → dirs ignorados → .gitignore.
3. **Chunking**: `RecursiveCharacterTextSplitter` com separadores sensíveis à linguagem (Rust, C++, Lua, Python, JSON). Padrão: 12000 chars / 1000 overlap.
4. **Cache**: Baseado em MD5 previne re-embedding de arquivos inalterados.
5. **Retry**: Arquivos com falha recebem 2 retries automáticos, depois aparecem em `error_files` para `retry_failed_files()` manual.

## Testes

- Framework: **pytest** com **pytest-asyncio**.
- Testes ficam em `tests/` espelhando a estrutura de `src/`.
- Testes do ModelGuard injetam uma instância limpa de `guard` — faça o mesmo para novos testes que toquem serialização Ollama.
- Ainda não existem testes de integração que requeiram Ollama/Postgres ativos. Se adicionar, marque com um marcador pytest descritivo.

## Ambiente

- **`.env`** controla: `OLLAMA_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `RAG_MODEL`, `VECTOR_STORE_TYPE`, credenciais Postgres.
- **Vector store**: Atualmente `postgres` (via Docker). Código legado ChromaDB pode existir mas não é o caminho ativo.
- **Postgres**: Container Docker `mcp-rust-star-db` na porta 5432. DB: `mcp_knowledge`, usuário: `user`, senha: `password`.
- **Windows**: `WinCompatRotatingFileHandler` lida com travamento de arquivos durante rotação de logs.

## Ferramentas MCP (pontos de entrada para clientes)

- **Gestão de projetos**: `register_project`, `list_projects`
- **Indexação**: `index_file`, `index_directory`, `batch_index_projects` (background por padrão), `scan_extensions`, `get_embed_status`, `cancel_embed`, `retry_failed_files`, `index_image`
- **RAG**: `ask_knowledge_base(question, project_id?)`
- **Vision**: `analyze_screenshot(path, save_to_kb?, context_hint?)`
- **Sistema**: `get_server_settings`, `update_indexing_settings`, `update_vision_settings`, `reset_server_settings`, `check_ollama_status`, `get_gpu_status`, `unload_vram`, `clear_knowledge_base`, `list_indexed_sources`

---

## Sistema de Regras, Skills e Documentação

> **IMPORTANTE**: Antes de iniciar qualquer tarefa, verifique se existe uma **regra** ou **skill** em `.agents/` que se aplica. Consulte-as ativamente — elas contêm protocolos obrigatórios que NÃO estão resumidos aqui.

### Como as Regras Funcionam (`.agents/rules/`)

As regras são contratos de comportamento que governam como o agente deve operar. São numeradas de 00 a 06 e devem ser consultadas conforme o tipo de tarefa:

| Regra | Arquivo | Quando consultar |
|---|---|---|
| **00** — Protocolo Stop & Think | `00-mcp-rust-star-overview.md` | **SEMPRE antes de começar**. Define o protocolo soberano: ler SESSION_LOG.md, validar escopo, aplicar grilling, usar linguagem ubíqua do CONTEXT.md. Também define: NUNCA usar `print()`, NUNCA `try/except: pass`, obrigatoriedade de documentação densa. |
| **01** — Integridade do Sistema | `01-mcp-system-integrity.md` | Ao criar novas ferramentas, lidar com erros, tocar em SQL/Postgres. Define níveis de log, isolamento stdout/stderr, tipagem obrigatória, isolamento de tabelas por projeto, transacionalidade em batch. |
| **02** — Grilling (Sabatina) | `02-elite-alignment-grilling.md` | **Antes de escrever código**. Obriga questionar premissas ocultas, estados de erro, limites de escopo, restrições de VRAM. Exige critérios de aceite validáveis antes de executar. |
| **03** — Loop de Diagnóstico | `03-disciplined-diagnostics.md` | **Ao investigar bugs**. 6 etapas obrigatórias: Reproduzir → Minimizar → Hipotetizar → Instrumentar → Corrigir → Teste de Regressão. Proíbe "tentativa e erro" sem evidência. |
| **04** — Fatiamento Vertical + ADRs | `04-vertical-slicing-and-adrs.md` | Ao planejar features grandes. Implemente de ponta a ponta em fatias finas. Toda decisão arquitetural deve gerar um ADR em `docs/adr/`. |
| **05** — Performance RAG | `05-rag-performance-and-metadata.md` | Ao mexer com indexação, busca vetorial, metadados, ou VRAM. Define enriquecimento de metadados por caminho, top-N contextual, threshold de similaridade, descarregamento proativo. |
| **06** — Arquitetura Limpa | `06-clean-architecture.md` | Ao modificar estrutura de camadas, adicionar novos módulos. Define separação interface/serviço/persistência, injeção de dependências, estado compartilhado unidirecional. |

### Como as Skills Funcionam (`.agents/skills/`)

Skills são guias especializados que o agente deve invocar via `skill` tool quando a tarefa se encaixa. Cada skill tem um `SKILL.md` com instruções detalhadas.

| Skill | Quando usar |
|---|---|
| **mcp-rust-star** | Operação do servidor RAG: catálogo completo de ferramentas, configurações, protocolos de boot, exemplos práticos, segurança de VRAM. Referência definitiva de operação. |
| **elite-engineering** | Práticas de engenharia de alto nível: linguagem ubíqua (CONTEXT.md), execução de grilling, loop de diagnóstico, gestão de ADRs, escrita incremental de docs, protocolo de diário de sessão. |
| **diagnose** | Bugs complexos e regressões de performance. Loop disciplinado: feedback loop → reproduzir → hipotetizar → instrumentar → corrigir + teste de regressão → cleanup + post-mortem. |
| **improve-codebase-architecture** | Refatorações, consolidação de módulos acoplados, melhorar testabilidade. Usa contexto do CONTEXT.md e ADRs existentes. |
| **triage** | Gestão de tarefas, bugs, débitos técnicos. Classificação e preparação de issues para agentes AFK. |
| **grill-me** | Stress-test de planos e designs. Entrevista relentlessly até chegar em entendimento compartilhado. |
| **grill-with-docs** | Stress-test contra o modelo de domínio existente. Atualiza CONTEXT.md e ADRs inline conforme decisões cristalizam. |
| **tdd** | Desenvolvimento com ciclo red-green-refactor. Ao construir features ou corrigir bugs com testes primeiro. |
| **to-issues** | Converter planos/specs em issues do tracker (GitHub ou markdown local). |
| **to-prd** | Transformar conversa atual em PRD e publicar no tracker. |
| **prototype** | Build de protótipo descartável para explorar design antes de commitar. |
| **write-a-skill** | Criar novas skills com estrutura correta, progressive disclosure e recursos bundled. |
| **handoff** | Compactar conversa atual em documento de handoff para outro agente. |
| **setup-matt-pocock-skills** | Configurar bloco `## Agent skills` e `docs/agents/` para skills de engenharia. |
| **zoom-out** | Dar perspectiva mais ampla sobre código ou arquitetura. |
| **caveman** | Modo ultra-comprimido de comunicação (quando solicitado). |

### Fluxo de Consulta Obrigatório

1. **Recebeu uma tarefa?** → Leia `docs/SESSION_LOG.md` para saber onde parou (Regra 00).
2. **A tarefa envolve código novo ou mudança?** → Consulte Regra 02 (Grilling) antes de codificar.
3. **É um bug ou falha?** → Use a skill `diagnose` + Regra 03 (Loop de Diagnóstico).
4. **É uma feature grande?** → Use Regra 04 (Fatiamento Vertical) + skill `to-issues`.
5. **Envolve indexação/RAG/VRAM?** → Consulte Regra 05 + skill `mcp-rust-star`.
6. **Envolve arquitetura/camadas?** → Consulte Regra 06 + skill `improve-codebase-architecture`.
7. **Precisa de termos do domínio?** → Consulte `CONTEXT.md`.
8. **Finalizou um ciclo?** → Atualize `docs/SESSION_LOG.md`.

### Documentação do Projeto

| Arquivo | Propósito |
|---|---|
| `CONTEXT.md` | Dicionário de linguagem ubíqua e limites de domínio (Rust Star, FoxOT, FoxClient). Consulte para traduzir pedidos vagos em termos técnicos. |
| `docs/SESSION_LOG.md` | Diário de sessão. **OBRIGATÓRIO** atualizar ao final de cada ciclo de trabalho. É o farol para a próxima sessão. |
| `docs/adr/` | Architecture Decision Records. Toda decisão que muda a trajetória do projeto deve gerar um ADR aqui. Formato: Contexto → Decisão → Consequências. |
| `docs/operation/` | Planos de operação e estabilização. |
| `docs/reports/` | Relatórios técnicos. |
| `GEMINI.md` | Visão geral do workspace, lista de ferramentas, mandatos. |
| `.agents/rules/` | Regras comportamentais (00-06) — consulte conforme a tabela acima. |
| `.agents/skills/` | Skills especializadas — consulte conforme a tabela acima. |

---

## Convenções

- **Evidência primeiro**: Consulte logs (`logs/mcp_error.log`) antes de hipotetizar correções.
- **Sem economia de tokens**: Não pule análise nem dê respostas superficiais. As regras em `.agents/rules/00-*` exigem mergulho profundo.
- **Indexação em batch**: Sempre rode `scan_extensions()` primeiro para verificar o que será indexado, depois `batch_index_projects()`.
- **Telemetria**: Dashboard lê `data/dashboard_state.json`. Apenas `TelemetryWriter` deve escrever nele.
- **Idioma**: Comunicação, documentos e planos sempre em pt-BR.
