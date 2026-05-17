name: mcp-rust-star
description: Manual Industrial Definitivo do ecossistema MCP Rust Star. Use para operar RAG multimodal, PostgreSQL, gestão de VRAM e filtros avançados com rigor técnico de 2026.

# 📔 Grimório de Operação: MCP Rust Star Knowledge Server (v1.2)

Este documento é a autoridade mestre para operação do servidor de conhecimento industrial. Ele detalha cada ferramenta, configuração e protocolo de elite para os projetos Rust Star, FoxOT e FoxClient.

---

## 🏗️ 1. Infraestrutura e Inicialização

O servidor utiliza uma arquitetura de **Alta Fidelidade**. Para detalhes técnicos sobre o setup do Docker, PostgreSQL e variáveis de ambiente, consulte o [Guia de Configuração (CONFIG_GUIDE.md)](CONFIG_GUIDE.md).

- **Banco de Dados**: PostgreSQL com extensão `pgvector`.
- **Inteligência**: Ollama local (qwen3-embedding:4b e qwen3.5:4b).
- **Transporte**: `streamable-http` em `http://127.0.0.1:8765/mcp` (padrão).
- **Monitoramento**: Dashboard em tempo real via `dashboard.bat` (UI Rich no Terminal).
- **Memória**: Janela calibrada de **12.288 tokens** (Equilíbrio VRAM/Precisão).

### 🔄 Protocolo de Boot

Execute via `scripts/start_server.bat` (HTTP - Principal) ou `scripts/start_server.ps1`.  
O servidor realiza **startup probes** automáticas antes de aceitar conexões:
1. Verifica porta `8765` livre (se estiver ocupada, o servidor HTTP já está ativo).
2. Verifica Ollama acessível em `http://127.0.0.1:11434`.
3. Verifica PostgreSQL acessível.

⚠️ **Incompatibilidade Crítica de Transporte**: O modo **HTTP é o principal**. Se o servidor HTTP estiver rodando, qualquer tentativa de carregar o modo **STDIO** (subprocesso local invocado pela IDE) falhará no boot, pois as probes de segurança abortam a execução ao detectar a porta `8765` ocupada. Para configurar corretamente o JSON de conexão da sua IDE (via HTTP ou STDIO), consulte o [Guia de Configuração (CONFIG_GUIDE.md)](CONFIG_GUIDE.md).

**Auto-detecção de transporte**: Quando o servidor é iniciado e não há concorrência de portas, se ele for chamado por uma IDE via JSON config (onde o `stdin` é um pipe), ele detecta automaticamente o modo STDIO. Se for iniciado no terminal de forma autônoma, adota o transporte HTTP.

---

## 🛠️ 2. Catálogo Completo de Ferramentas (Tools)

### 📁 Gestão de Projetos

| Ferramenta | Parâmetros | Descrição |
| :--- | :--- | :--- |
| `register_project` | `project_id` (str), `path` (str) | Vincula um nome a um diretório físico. **Obrigatório antes de indexar.** |
| `list_projects` | — | Retorna todos os workspaces registrados, caminhos e validade do path. |

### 🧠 Indexação e Embed

| Ferramenta | Parâmetros | Descrição |
| :--- | :--- | :--- |
| `index_file` | `path` (str) | Indexa um arquivo individual. Detecta o projeto automaticamente pelo path. |
| `index_directory` | `path` (str), `extension` (str, opt) | Indexa pasta completa respeitando filtros e `.gitignore`. Bloqueante. |
| `batch_index_projects` | `project_ids` (list, opt), `force` (bool), `background` (bool=True) | **Motor principal**. Indexa múltiplos projetos sequencialmente. Por padrão roda em background — servidor continua respondendo. Projetos adicionados enquanto embed roda são enfileirados automaticamente. |
| `scan_extensions` | `project_ids` (list, opt) | Escaneia projetos e lista extensões encontradas **SEM indexar nada**. Use antes de `batch_index_projects` para confirmar o que será processado. |
| `get_embed_status` | — | Status em tempo real do embed em background: projeto atual, arquivo atual, progresso, log das últimas linhas. **Não bloqueante.** |
| `cancel_embed` | — | Cancela o embed em andamento de forma segura (arquivo atual termina antes de parar). |
| `retry_failed_files` | — | Reprocessa arquivos que falharam na última sessão de indexação. |

### 👁️ Visão e Multimodal

| Ferramenta | Parâmetros | Descrição |
| :--- | :--- | :--- |
| `index_image` | `path` (str) | Indexa imagem usando Vision (qwen3.5). Gera texto descritivo e salva na KB. |
| `analyze_screenshot` | `path` (str), `save_to_kb` (bool=True), `context_hint` (str) | Analisa screenshot com Vision e salva na KB. `context_hint` orienta a análise (ex: "tela de erro de compilação"). |

### 🔍 Recuperação e Resposta (RAG)

| Ferramenta | Parâmetros | Descrição |
| :--- | :--- | :--- |
| `ask_knowledge_base` | `question` (str), `project_id` (str, opt) | Consulta principal. Recupera Top-K fragmentos para síntese. `project_id=None` busca em todos os workspaces. |
| `list_indexed_sources` | `project_id` (str, opt) | Lista arquivos indexados na KB. Útil para confirmar cobertura do embed. |

### ⚙️ Configurações do Servidor

| Ferramenta | Parâmetros | Descrição |
| :--- | :--- | :--- |
| `get_server_settings` | — | Mostra JSON completo das configurações ativas (indexação, Vision, chunks). |
| `update_indexing_settings` | `ignored_extensions` (list, opt), `chunk_size` (int, opt), `chunk_overlap` (int, opt) | Altera filtros de extensão e tamanhos de chunk em tempo real. |
| `update_vision_settings` | `auto_index_images` (bool, opt), `allowed_image_extensions` (list, opt), `auto_index_folders` (list, opt) | Configura o comportamento do Vision/multimodal. |
| `reset_server_settings` | — | Restaura todas as configurações ao padrão de fábrica. |

### 🖥️ Hardware e Sistema

| Ferramenta | Parâmetros | Descrição |
| :--- | :--- | :--- |
| `check_ollama_status` | — | Verifica conectividade do Ollama e lista modelos carregados. |
| `get_gpu_status` | — | Relatório em tempo real de VRAM (nvidia-smi). |
| `unload_vram` | — | **Ejeção de emergência**: solicita ao Ollama que descarregue todos os modelos da GPU. |
| `clear_knowledge_base` | `project_id` (str, opt) | Reset cirúrgico (`project_id` específico) ou total (sem parâmetro) da base de dados. |

---

## ⚙️ 3. Manual de Configuração

Você pode ajustar estes valores via `update_indexing_settings` e `update_vision_settings`:

1. **`ignored_extensions`**: Extensões ignoradas no `batch_index_projects` / `index_directory`.
   - *Padrão*: `[".log", ".exe", ".dll", ".pyc"]` + pastas ocultas e `.gitignore`.
2. **`chunk_size`**: Tamanho de cada fragmento (Padrão: 12.000 chars).
3. **`chunk_overlap`**: Sobreposição para manter continuidade semântica (Padrão: 1.000 chars).
4. **`auto_index_images`**: Se `True`, o embed indexa imagens automaticamente.
5. **`allowed_image_extensions`**: Extensões de imagem reconhecidas (ex: `[".png", ".jpg"]`).
6. **`auto_index_folders`**: Pastas onde imagens são sempre indexadas independente de `auto_index_images`.

---

## 💡 4. Exemplos Práticos de Elite

### Caso A: Fluxo completo de onboarding de novo projeto
```
1. register_project("FoxClient", "C:/Projetos/FoxClient")
2. scan_extensions(["FoxClient"])          → confirma extensões
3. update_indexing_settings(ignored_extensions=[".tmp", ".bak"])  → se necessário
4. batch_index_projects(["FoxClient"])     → inicia em background
5. get_embed_status()                      → monitora progresso
```

### Caso B: Diagnóstico Multimodal de Erro
> "Tirei um print do erro de compilação. Analise e indexe."
- `analyze_screenshot(path="C:/prints/error_01.png", context_hint="erro de compilação Rust")`

### Caso C: Consulta RAG Global
> "Qual a lógica de conexão com o banco de dados em todos os meus projetos?"
- `ask_knowledge_base(question="...", project_id=None)` — busca em todos os workspaces.

### Caso D: Reindexação forçada após mudança grande
- `batch_index_projects(project_ids=["Rust Star"], force=True)`

---

## 🛡️ 5. Protocolos de Segurança e Performance

- **Zero-Waste VRAM**: Após embed, o servidor descarrega modelos automaticamente via `unload_models()`. Use `unload_vram()` se a VRAM não liberar.
- **Estabilidade por Subdivisão**: Arquivos que saturam a VRAM são divididos recursivamente.
- **Isolamento de Contexto**: Nunca responda pergunta de um projeto usando dados de outro sem permissão explícita.
- **Fila de Embed**: Chamar `batch_index_projects` durante embed ativo adiciona à fila — não inicia instância paralela.
- **Integridade de Log**: Consulte `logs/mcp_error.log` ou acompanhe o Dashboard (`dashboard.bat`).
- **Endpoints de observabilidade**: `GET /health`, `GET /events/stream` (SSE), `GET /events/recent`, `GET /metrics` disponíveis enquanto o servidor HTTP estiver ativo.

---
*Este manual é um artefato de Engenharia de Elite. Siga-o para garantir a soberania do conhecimento no ecossistema Rust Star.*
