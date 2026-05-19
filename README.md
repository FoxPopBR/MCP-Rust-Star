# MCP Rust Star — Knowledge Server

> Servidor de base de conhecimento RAG local, projetado para projetos de desenvolvimento de jogos. Indexa código-fonte, documentação e imagens de múltiplos projetos e responde perguntas técnicas com citação de fontes — tudo offline, sem nuvem, com GPU local.

---

## Sumário

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Pré-requisitos](#pré-requisitos)
4. [Instalação Passo a Passo](#instalação-passo-a-passo)
5. [Configuração](#configuração)
   - [Variáveis de Ambiente (.env)](#variáveis-de-ambiente-env)
   - [Configurações Avançadas (defaults.json)](#configurações-avançadas-defaultsjson)
   - [Preferências do Usuário](#preferências-do-usuário)
6. [Iniciando o Servidor](#iniciando-o-servidor)
7. [Conectando ao Claude / Gemini](#conectando-ao-claude--gemini)
8. [Referência Completa de Ferramentas](#referência-completa-de-ferramentas)
   - [Gestão de Projetos](#gestão-de-projetos)
   - [Indexação](#indexação)
   - [Busca e RAG](#busca-e-rag)
   - [Análise Visual (Vision)](#análise-visual-vision)
   - [Sistema e Hardware](#sistema-e-hardware)
   - [Configuração em Tempo Real](#configuração-em-tempo-real)
9. [Sistema de Segurança e Controle de VRAM](#sistema-de-segurança-e-controle-de-vram)
10. [Pipeline RAG Detalhado](#pipeline-rag-detalhado)
11. [Sistema de Cache](#sistema-de-cache)
12. [Dashboard de Monitoramento](#dashboard-de-monitoramento)
13. [Estrutura de Arquivos](#estrutura-de-arquivos)
14. [Banco de Dados](#banco-de-dados)
15. [Otimizações de GPU (8 GB VRAM)](#otimizações-de-gpu-8-gb-vram)
16. [Solução de Problemas](#solução-de-problemas)

---

## Visão Geral

O **MCP Rust Star Knowledge Server** é um servidor [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) que transforma pastas de projetos em bases de conhecimento pesquisáveis por linguagem natural.

**O que ele faz:**
- Lê e divide arquivos de código (``.rs``, ``.cpp``, ``.py``, ``.lua``, ``.md``, PDFs e muito mais) em chunks semânticos
- Gera embeddings vetoriais com Ollama e persiste no PostgreSQL + pgvector
- Responde perguntas técnicas usando RAG (Retrieval-Augmented Generation) com citação de arquivo e linha
- Analisa screenshots e imagens técnicas via modelo multimodal local
- Expõe todas as funcionalidades como ferramentas MCP para Claude, Gemini ou qualquer cliente compatível

**Projetos indexados por padrão:**
| ID | Projeto |
|---|---|
| `rust_star` | Engine MMORPG em Rust (WGPU/ECS) |
| `foxot` | Servidor Tibia customizado em C++ |
| `foxclient` | Cliente Tibia personalizado |
| `nova_rust` | Nova engine (iteração do Rust Star) |
| `mcp_rust_star` | Este próprio servidor |

Você pode registrar qualquer pasta como projeto adicional.

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                   Cliente MCP (Claude / Gemini)              │
└──────────────────────────┬──────────────────────────────────┘
                           │  HTTP (streamable-http ou SSE)
                           │  http://127.0.0.1:8765/mcp
┌──────────────────────────▼──────────────────────────────────┐
│                    FastMCP Server                            │
│   src/main.py — 20+ ferramentas MCP                         │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  RAGService │  │  ModelGuard  │  │   EventBus        │  │
│  │  (pipeline) │  │  (serializa  │  │   (pub/sub        │  │
│  │             │  │   Ollama)    │  │    telemetria)    │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬──────────┘  │
│         │                │                    │              │
│  ┌──────▼──────┐  ┌──────▼───────┐  ┌────────▼──────────┐  │
│  │ OllamaClient│  │ ConfigManager│  │ TelemetryWriter   │  │
│  │  (embed +   │  │  (defaults + │  │  (snapshot +      │  │
│  │   chat +    │  │   prefs)     │  │   heartbeat)      │  │
│  │   vision)   │  └──────────────┘  └───────────────────┘  │
│  └──────┬──────┘                                            │
└─────────│───────────────────────────────────────────────────┘
          │
┌─────────▼──────────────┐     ┌──────────────────────────────┐
│      Ollama             │     │   PostgreSQL + pgvector      │
│  (LLM local)           │     │   Docker: mcp-rust-star-db   │
│                        │     │   Banco: mcp_knowledge        │
│  Modelos:              │     │                              │
│  • qwen3-embedding:4b  │     │  Tabelas:                    │
│    (2560 dims)         │     │  • rag_rust_star             │
│  • qwen3.5:4b          │     │  • rag_foxot                 │
│    (chat + vision)     │     │  • rag_foxclient             │
│                        │     │  • rag_<projeto>             │
│  Contexto: 32768 tokens│     │  (uma por projeto)           │
│  Flash Attention: ON   │     │                              │
└────────────────────────┘     └──────────────────────────────┘
```

**Fluxo de dados:**
1. Ferramenta MCP chama `batch_index_projects()`
2. Worker background divide arquivos em chunks (12 000 chars / overlap 1 000)
3. Cada chunk é enviado ao `qwen3-embedding:4b` → vetor de 2560 dimensões
4. Vetor + metadados (source, project_id, hash MD5) salvos no PostgreSQL
5. Ao fazer busca, a pergunta é embedada, busca cosine similarity, top-5 retornados
6. `qwen3.5:4b` gera resposta final com os fragmentos como contexto

---

## Pré-requisitos

| Componente | Versão mínima | Notas |
|---|---|---|
| Python | 3.10+ | Recomendado 3.11+ |
| Docker Desktop | qualquer recente | Para o container PostgreSQL |
| Ollama | 0.6+ | Deve rodar antes do servidor |
| VRAM | 6 GB | 8 GB recomendado para conforto |
| RAM | 16 GB | 8 GB usados como overflow de contexto |
| OS | Windows 10/11 | Linux também funciona |

**Modelos Ollama necessários:**
```bash
ollama pull qwen3-embedding:4b
ollama pull qwen3.5:4b
```

> O `qwen3-embedding:4b` ocupa ~2.7 GB de VRAM. O `qwen3.5:4b` ocupa ~3.4 GB.
> Com Flash Attention e KV cache q8_0, ambos cabem nos 8 GB durante o embed.
> O ModelGuard garante que nunca rodem simultaneamente.

---

## Instalação Passo a Passo

### 1. Clone ou baixe o projeto

```bash
git clone <url-do-repo> "C:\Phantasy\MCP Rust Star"
cd "C:\Phantasy\MCP Rust Star"
```

### 2. Crie o ambiente virtual Python

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Suba o banco de dados PostgreSQL

```bash
docker compose up -d
```

Isso inicia o container `mcp-rust-star-db` com pgvector. O healthcheck verifica automaticamente se o PostgreSQL está pronto antes de prosseguir.

**Verificação:**
```bash
docker exec mcp-rust-star-db pg_isready -U user -d mcp_knowledge
# Resposta esperada: localhost:5432 - accepting connections
```

### 4. Configure o arquivo `.env`

Copie ou edite o `.env` na raiz do projeto:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
EMBEDDING_MODEL=qwen3-embedding:4b
EMBEDDING_DIM=2560
RAG_MODEL=qwen3.5:4b
VISION_MODEL=qwen3.5:4b
CHUNK_SIZE=12000

VECTOR_STORE_TYPE=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=mcp_knowledge
POSTGRES_USER=user
POSTGRES_PASSWORD=password
```

### 5. Inicie o Ollama

```bash
ollama serve
```

(Em Windows, o Ollama geralmente já está rodando como serviço na bandeja do sistema.)

### 6. Inicie o servidor MCP

```bat
run_server.bat
```

O script realiza 5 verificações automáticas antes de subir:
1. Valida o venv Python
2. Confirma que Docker está acessível
3. Garante que o container PostgreSQL está rodando (e sobe se necessário)
4. Valida as dependências Python
5. Inicia o servidor em `http://127.0.0.1:8765`

---

## Configuração

### Variáveis de Ambiente (.env)

| Variável | Padrão | Descrição |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | URL do servidor Ollama |
| `EMBEDDING_MODEL` | `qwen3-embedding:4b` | Modelo para gerar embeddings |
| `EMBEDDING_DIM` | `2560` | Dimensão dos vetores (deve corresponder ao modelo) |
| `RAG_MODEL` | `qwen3.5:4b` | Modelo para geração de respostas e visão |
| `VISION_MODEL` | `qwen3.5:4b` | Modelo para análise de imagens |
| `CHUNK_SIZE` | `12000` | Tamanho máximo de chunk em caracteres |
| `CHUNK_OVERLAP` | `1000` | Sobreposição entre chunks (contexto de continuidade) |
| `VECTOR_STORE_TYPE` | `postgres` | Tipo de store vetorial |
| `POSTGRES_HOST` | `localhost` | Host do PostgreSQL |
| `POSTGRES_PORT` | `5432` | Porta do PostgreSQL |
| `POSTGRES_DB` | `mcp_knowledge` | Nome do banco de dados |
| `POSTGRES_USER` | `user` | Usuário PostgreSQL |
| `POSTGRES_PASSWORD` | `password` | Senha PostgreSQL |

### Configurações Avançadas (defaults.json)

Localizado em `src/resources/defaults.json`. Contém os padrões de fábrica que podem ser sobrescritos em tempo real.

**Seção `indexing`:**
```json
{
  "chunk_size": 12000,
  "chunk_overlap": 1000,
  "use_gitignore": true,
  "ignored_extensions": [".exe", ".dll", ".png", ".mp3", "..."],
  "ignored_dirs": [".git", "node_modules", "target", "build", "..."]
}
```

**Extensões indexadas por padrão:**
`.rs`, `.c`, `.cpp`, `.h`, `.hpp`, `.lua`, `.py`, `.md`, `.txt`, `.json`, `.toml`, `.yaml`, `.yml`, `.ini`, `.sh`, `.xml`, `.html`, `.css`, `.js`, `.ts`, `.jsx`, `.tsx`, `.sql`, `.proto`, `.otmod`, `.otui`, `.frag`, `.vert`

**Seção `rag`:**
```json
{
  "n_results": 5,
  "context_window": 32768,
  "distance_threshold": 0.75
}
```

**Seção `vision`:**
```json
{
  "auto_index_images": false,
  "auto_index_folders": [],
  "allowed_image_extensions": [".png", ".jpg", ".jpeg"]
}
```

### Preferências do Usuário

O arquivo `data/user_preferences.json` armazena sobrescritas persistidas pelo usuário via ferramentas MCP (ex: `update_indexing_settings`). Ele tem prioridade sobre `defaults.json` e é mesclado em tempo real.

Para resetar tudo para os padrões de fábrica, use a ferramenta `reset_server_settings()`.

---

## Iniciando o Servidor

### Modo interativo (recomendado para desenvolvimento)

```bat
run_server.bat
```

Mantém a janela aberta com log visível. CTRL+C encerra graciosamente (descarrega VRAM, fecha conexões, remove PID file).

### Modo MCP silencioso (para clientes como Claude Code)

```bat
run_server.bat --mcp
```

Sem janela interativa. Todo output vai para `logs/startup.log` e `logs/mcp_error.log`.

### Verificando se está rodando

```bash
curl http://127.0.0.1:8765/health
# ou
curl http://127.0.0.1:8765/telemetry
```

---

## Conectando ao Claude / Gemini

### Claude Code (VS Code / Desktop)

Adicione ao seu arquivo de configuração MCP (`mcp_config_local.json` ou settings globais do Claude):

```json
{
  "mcpServers": {
    "mcp-rust-star": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

### Gemini (antigravity / IDE)

Use o arquivo `mcp_config_local.json` na raiz do projeto — o Gemini o detecta automaticamente.

### Verificação da conexão

Após conectar, use a ferramenta:
```
check_ollama_status()
```

Deve retornar:
```
✓ Ollama CONECTADO (http://127.0.0.1:11434)
  Embedding (qwen3-embedding:4b): ✓
  RAG/Vision (qwen3.5:4b): ✓
```

---

## Referência Completa de Ferramentas

### Gestão de Projetos

#### `register_project(project_id, path)`
Registra uma pasta no disco como projeto indexável. Obrigatório antes de qualquer indexação.

```
register_project("rust_star", "C:\Phantasy\Nova Rust")
```

- Valida que o caminho existe e é um diretório
- Persiste em `data/projects.json`
- Detecção automática de projeto pelo caminho: quando você indexa um arquivo, o servidor identifica a qual projeto ele pertence pelo longest-match do caminho

---

#### `list_projects()`
Lista todos os projetos registrados com status de validade do caminho.

```
Projetos registrados (4):
  [✓] foxclient: C:\Phantasy\FoxClient
  [✓] foxot: C:\Phantasy\FoxOT
  [✗] antigo: C:\Phantasy\Deletado  (caminho inválido)
  [✓] rust_star: C:\Phantasy\Nova Rust
```

---

### Indexação

#### `batch_index_projects(project_ids, force, background)`
**Ferramenta principal de indexação.** Indexa múltiplos projetos em background com progresso persistido.

| Argumento | Padrão | Descrição |
|---|---|---|
| `project_ids` | `null` | Lista de IDs. `null` = todos os projetos |
| `force` | `false` | `true` reprocessa projetos já indexados |
| `background` | `true` | `false` bloqueia até concluir (útil em scripts) |

**Funcionalidades:**
- **Background por padrão**: o servidor MCP continua respondendo durante o embed
- **Fila dinâmica**: se chamado enquanto embed está rodando, adiciona à fila
- **Retomada automática**: crash durante indexação? Execute novamente — projetos concluídos são pulados automaticamente (arquivo `data/batch_progress.json`)
- **Cache MD5**: arquivos com conteúdo não alterado são pulados (cache hit)
- **Garbage collection**: ao escanear um projeto completo, remove automaticamente do banco vetores de arquivos que foram deletados ou movidos ("fantasmas")
- **Retry automático**: arquivos que falham na primeira tentativa são adicionados à fila de retry (até 2 tentativas)

```
batch_index_projects(["rust_star", "foxot"])
→ ✓ Embed iniciado em background!
  Projetos na fila: ['rust_star', 'foxot']
  Use get_embed_status() para acompanhar o progresso.
```

---

#### `get_embed_status()`
Retorna o status em tempo real do embed em andamento.

```
⟳ STATUS: EM ANDAMENTO
Duração: 0:04:32
Projeto: rust_star
Arquivo: game_loop.rs

Estatísticas:
  ✓ 847 novos | ⊙ 1203 cache | ✗ 2 erros
```

---

#### `cancel_embed()`
Cancela o embed após o arquivo atual terminar. Nunca interrompe no meio de um arquivo para evitar chunks incompletos. O progresso já salvo é preservado para retomada futura.

---

#### `retry_failed_files()`
Re-indexa arquivos que falharam durante o último embed. Use `get_embed_status()` para ver a lista de erros antes.

---

#### `index_file(path)`
Indexa um arquivo individual. Detecta o projeto automaticamente pelo caminho.

```
index_file("C:\Phantasy\Nova Rust\src\game_loop.rs")
```

Suporta todos os formatos de texto (`.rs`, `.cpp`, `.py`, `.md`, `.pdf`, etc.).

---

#### `index_directory(path, extension)`
Indexa um diretório completo respeitando `.gitignore` e filtros de extensão.

```
index_directory("C:\Phantasy\FoxOT\src", extension=".cpp")
```

---

#### `index_image(path)`
Indexa uma imagem manualmente via Vision multimodal. Gera descrição textual e salva na base de conhecimento do projeto correspondente.

---

#### `scan_extensions(project_ids)`
Escaneia projetos e lista todas as extensões encontradas **sem indexar nada**. Use antes de `batch_index_projects` para confirmar o que será processado e configurar extensões a ignorar.

```
═══ SCAN DE EXTENSÕES ═══
Projetos: ['rust_star']
Total de arquivos elegíveis: 2847

✓ SERÃO INDEXADOS (12 tipos, 2847 arquivo(s)):
   .rs               1203 arquivo(s)
   .toml              847 arquivo(s)
   .md                412 arquivo(s)
   ...

○ JÁ NA LISTA DE IGNORADOS (3 tipos, 150 arquivo(s)):
   .png               150 arquivo(s)
```

---

### Busca e RAG

#### `search_project_knowledge(project_id, question)` ⭐ Principal
**Ferramenta recomendada para a maioria das buscas.** Rápida, isolada por projeto.

```
search_project_knowledge("rust_star", "como funciona o sistema de combate?")
```

- Embeda a pergunta, busca por similaridade cosine no projeto especificado
- Retorna os top-5 fragmentos mais relevantes (configurável)
- Processa em background e salva resultado em `logs/rag_history/<project_id>/`
- Suporta cache: perguntas repetidas retornam instantaneamente

---

#### `search_all_projects_knowledge(question)` ⚠️ Lenta
Busca em **todos** os projetos simultaneamente. Use apenas quando não souber qual projeto contém a informação.

---

#### `cross_project_analysis(searches_json, analysis_prompt)`
Busca em múltiplos projetos e gera análise cruzada comparativa.

```
cross_project_analysis(
  '[{"project_id": "rust_star", "query": "sistema de inventário"},
    {"project_id": "foxot", "query": "sistema de inventário"}]',
  "Compare as diferenças de implementação entre os dois projetos."
)
```

Executa as buscas sequencialmente (uma de cada vez) para não sobrecarregar a VRAM, depois combina e gera análise unificada.

---

#### `ask_knowledge_base(question, project_id)`
Interface genérica de busca RAG. Funciona igual ao `search_project_knowledge` mas com `project_id` opcional (para compatibilidade).

---

#### `list_indexed_sources(project_id)`
Lista todos os arquivos-fonte únicos indexados na base de conhecimento.

```
Fontes indexadas (1847 únicas) — todos os projetos:

  [rust_star] — 1203 arquivo(s):
    • C:\Phantasy\Nova Rust\src\combat\damage.rs
    • C:\Phantasy\Nova Rust\src\game_loop.rs
    • ...
```

---

### Análise Visual (Vision)

#### `analyze_screenshot(path, save_to_kb, context_hint)`
Analisa um screenshot técnico usando o modelo multimodal.

| Argumento | Padrão | Descrição |
|---|---|---|
| `path` | — | Caminho da imagem (PNG/JPG) |
| `save_to_kb` | `true` | Salva análise na base de conhecimento |
| `context_hint` | `""` | Contexto adicional sobre o conteúdo esperado |

Especializado em:
- Erros de compilação Rust (`cargo build` output)
- Bugs de renderização WGPU (artefatos visuais, profiling)
- Logs do servidor
- Crash dumps e stack traces
- Estado do mapa do jogo
- Diagramas de arquitetura

```
analyze_screenshot(
  "C:\screenshots\wgpu_artifact.png",
  context_hint="Erro de renderização no sistema de tiles"
)
```

---

### Sistema e Hardware

#### `check_ollama_status()`
Verifica conexão com Ollama e disponibilidade dos modelos configurados. Útil para diagnóstico rápido.

---

#### `get_gpu_status()`
Verifica uso atual de VRAM via `nvidia-smi`. Retorna uso por processo, temperatura e clock.

---

#### `unload_vram()`
**Ejeção de emergência.** Descarrega todos os modelos Ollama da VRAM imediatamente. Use quando a VRAM estiver travada ou para liberar memória antes de rodar outro programa pesado.

---

#### `clear_knowledge_base(project_id)`
Apaga vetores do banco de dados.

- Com `project_id`: limpa apenas aquele projeto
- Sem argumento: limpa **tudo** (todos os projetos)

---

### Configuração em Tempo Real

#### `get_server_settings()`
Retorna relatório JSON completo de todas as configurações ativas (fábrica + overrides do usuário).

---

#### `update_indexing_settings(...)`
Atualiza configurações de indexação e persiste em `data/user_preferences.json`.

| Argumento | Tipo | Descrição |
|---|---|---|
| `ignored_extensions` | `list` | Extensões a ignorar. **Sobrescreve a lista atual** |
| `ignored_dirs` | `list` | Nomes de diretórios a ignorar |
| `use_gitignore` | `bool` | Respeitar `.gitignore` dos projetos |
| `chunk_size` | `int` | Tamanho máximo de chunk (chars) |
| `chunk_overlap` | `int` | Overlap entre chunks (chars) |

```
update_indexing_settings(
  ignored_extensions=[".log", ".tmp", ".cache"],
  chunk_size=8000
)
```

---

#### `update_vision_settings(auto_index_images, auto_index_folders)`
Configura a indexação automática de imagens durante o embed.

- `auto_index_images=true`: todas as imagens de todos os projetos são analisadas
- `auto_index_folders=["/path/screenshots"]`: apenas imagens nestas pastas específicas

---

#### `reset_server_settings()`
Restaura **todas** as configurações para os padrões de fábrica. Remove `data/user_preferences.json`.

---

## Sistema de Segurança e Controle de VRAM

### ModelGuard

O **ModelGuard** é o sistema central de controle de concorrência para operações Ollama. Garante que apenas **uma operação de modelo** (embed, chat ou vision) execute por vez, evitando out-of-memory na VRAM.

**Tipos de operação (kinds):**
| Kind | Operações |
|---|---|
| `embed` | Geração de embeddings, buscas RAG, indexação de arquivos |
| `chat` | Geração de respostas (RAG query) |
| `vision` | Análise de imagens, indexação de screenshots |

**Comportamento:**
1. Operação tenta adquirir o lock
2. Se lock ocupado, entra na fila e emite evento `model.queued`
3. Ao adquirir, emite `model.acquired` com tempo de espera
4. Ao liberar, emite `model.released` com tempo de execução
5. **Lookahead proativo**: durante o embed, o sistema verifica o próximo item na fila — se for de um `kind` diferente (ex: busca RAG chegou enquanto embed roda), descarrega proativamente a VRAM para o próximo modelo carregar sem OOM

```python
# Exemplo interno do lookahead
next_kind = get_model_guard().peek_next_kind()
if next_kind is not None and next_kind != "embed":
    await asyncio.to_thread(rag.ollama.unload_models)
```

### Descarregamento Automático de VRAM

Após cada operação de embedding ou geração, o modelo é descarregado da VRAM automaticamente. Isso permite que o sistema opere com GPUs de 6–8 GB sem ocupar VRAM permanentemente.

**Quando ocorre:**
- Após cada arquivo indexado (durante batch embed)
- Após cada resposta RAG gerada
- Após cada análise de imagem
- Ao encerrar o servidor (via `handle_exit`)
- Via ferramenta `unload_vram()` (emergência)

### EventBus

O **EventBus** é o sistema de pub/sub interno que conecta o servidor MCP ao dashboard e à telemetria sem acoplamento direto.

**Eventos principais:**
| Evento | Quando |
|---|---|
| `server.started` / `server.stopped` | Lifecycle do servidor |
| `tool.invoked` / `tool.completed` / `tool.failed` | Cada chamada de ferramenta |
| `embed.batch.progress` | Progresso salvo no batch |
| `embed.batch.finished` | Batch concluído |
| `embed.file.processing` | Arquivo sendo processado |
| `embed.cancelled` | Embed cancelado pelo usuário |
| `embed.log.appended` | Nova linha no buffer de log |
| `rag.query.received` | Pergunta RAG recebida |
| `rag.state.changed` | Estado interno do RAG mudou |
| `model.queued` | Operação aguardando ModelGuard |
| `model.acquired` | Lock adquirido |
| `model.released` | Lock liberado |

### Lifecycle e PID File

O servidor escreve seu PID em `data/server.pid` ao iniciar e remove ao encerrar. O `run_server.bat` usa isso para garantir que instâncias anteriores sejam terminadas antes de subir uma nova.

---

## Pipeline RAG Detalhado

### 1. Indexação

```
Arquivo (.rs, .py, .md, etc.)
         ↓
    Leitura binária (UTF-8 com fallback)
         ↓
    PDF? → pypdf para extração de texto
         ↓
    RecursiveCharacterTextSplitter
    (chunk_size=12000, overlap=1000)
         ↓
    Para cada chunk:
      ┌─ MD5 hash do conteúdo
      ├─ Já existe no banco? → Cache Hit (pula)
      └─ Novo? → OllamaClient.get_embedding()
                      ↓
              qwen3-embedding:4b
              (2560 dims, num_ctx=32768)
                      ↓
              PostgresStore.upsert()
              (tabela rag_<project_id>)
```

### 2. Busca RAG

```
Pergunta do usuário
         ↓
    _check_raw_cache() → Já respondeu isso? → Cache Hit → retorna arquivo
         ↓
    OllamaClient.get_embedding(pergunta)
         ↓
    PostgresStore.search(embedding, project_id, n=5)
    (cosine similarity, threshold=0.75)
         ↓
    Fragmentos ordenados por relevância
         ↓
    Monta prompt com os fragmentos como contexto
         ↓
    OllamaClient.chat(qwen3.5:4b, prompt)
    (num_ctx=32768, Flash Attention)
         ↓
    Salva resultado em logs/rag_history/<project>/query_<ts>.md
         ↓
    Retorna caminho do arquivo ao usuário
```

### Chunking Inteligente

O `RecursiveCharacterTextSplitter` divide o texto seguindo esta hierarquia de separadores:
1. `\n\n` (parágrafos)
2. `\n` (linhas)
3. ` ` (palavras)
4. `` (caracteres)

Com `chunk_size=12000` e `chunk_overlap=1000`, cada chunk cobre aproximadamente 3000 tokens, deixando espaço generoso no contexto de 32k tokens para múltiplos fragmentos + a pergunta.

---

## Sistema de Cache

### Cache de Embeddings (MD5)

Cada arquivo indexado tem seu hash MD5 armazenado. Na próxima indexação:
- Hash igual → Cache Hit → chunks pulados (não re-embedados)
- Hash diferente → conteúdo mudou → re-indexa

Isso garante que re-indexar um projeto enorme seja rápido na segunda vez.

### Cache de Respostas RAG

Respostas RAG são cacheadas por pergunta normalizada (lowercase, sem pontuação) + project_id. O índice de cache fica em `logs/rag_history/index.json`.

```json
{
  "rust_star:como funciona o sistema de combate": {
    "file": "logs/rag_history/rust_star/query_2026-05-18_14-32-11.md",
    "ts": "2026-05-18T14:32:11"
  }
}
```

Perguntas cacheadas retornam **instantaneamente** sem consumir VRAM.

### Persistência do Progresso de Batch

O arquivo `data/batch_progress.json` registra quais projetos foram indexados com sucesso. Em caso de crash ou cancelamento:

```bash
# Retoma de onde parou (projetos concluídos são pulados)
batch_index_projects()

# Força reprocessamento completo
batch_index_projects(force=True)
```

---

## Dashboard de Monitoramento

O dashboard é uma aplicação Flask separada que monitora o servidor em tempo real via EventBus e polling HTTP.

**Iniciando o dashboard:**
```bat
dashboard.bat
```

Disponível em `http://127.0.0.1:5000`.

**O que mostra:**
- Status do servidor (online/offline)
- Embed em andamento: projeto atual, arquivo atual, estatísticas
- Uso de VRAM (polling nvidia-smi)
- Últimas queries RAG
- Inventário do banco (quantos chunks por projeto)
- Log em tempo real do embed

**Princípios do dashboard:**
- Nunca interfere com o servidor MCP (lê dados apenas via HTTP e EventBus)
- Não acessa GPU diretamente (evita conflito de VRAM)
- Tem seu próprio log separado (`logs/dashboard.log`)

---

## Estrutura de Arquivos

```
MCP Rust Star/
├── .env                          ← Configurações de ambiente (modelos, banco)
├── .venv/                        ← Ambiente virtual Python
├── docker-compose.yml            ← Container PostgreSQL + pgvector
├── run_server.bat                ← Script de inicialização (5 checks automáticos)
├── dashboard.bat                 ← Inicia o dashboard de monitoramento
├── requirements.txt              ← Dependências Python
├── mcp_config_local.json         ← Config MCP para Claude/Gemini
│
├── src/
│   ├── main.py                   ← Entrada do servidor, definição das 20+ ferramentas MCP
│   ├── ollama_client.py          ← Cliente Ollama (embed + chat + vision + unload)
│   ├── vector_store_postgres.py  ← PostgreSQL + pgvector (pool de 15 conexões)
│   ├── config_manager.py         ← Gerenciador de configurações (factory + user prefs)
│   ├── resources/
│   │   └── defaults.json         ← Padrões de fábrica (extensões, chunking, RAG)
│   └── services/
│       ├── rag_service.py        ← Pipeline RAG (index, search, cache, GC)
│       ├── model_guard.py        ← Serialização de acesso ao Ollama (ADR-0016)
│       ├── event_bus.py          ← Pub/sub in-process para telemetria
│       ├── telemetry_writer.py   ← Snapshots e heartbeat para o dashboard
│       ├── observability.py      ← Endpoints HTTP (/health, /telemetry)
│       └── lifecycle.py          ← PID file, drain do ModelGuard no shutdown
│
├── data/
│   ├── projects.json             ← Projetos registrados (gerado em runtime)
│   ├── defaults.json             ← Cópia dos padrões carregada pelo servidor
│   ├── user_preferences.json     ← Sobrescritas do usuário (gerado ao usar update_*)
│   ├── batch_progress.json       ← Progresso do embed (gerado durante indexação)
│   └── server.pid                ← PID do processo (gerado em runtime)
│
├── dashboard/
│   ├── app.py                    ← Aplicação Flask do dashboard
│   └── fetcher.py                ← Polling de telemetria e VRAM
│
├── logs/
│   ├── mcp_error.log             ← Log principal do servidor MCP
│   ├── startup.log               ← Log de inicialização
│   └── rag_history/
│       ├── index.json            ← Índice de cache de respostas RAG
│       ├── <project_id>/
│       │   └── query_<ts>.md     ← Respostas RAG salvas como markdown
│       └── global/
│           └── query_<ts>.md     ← Respostas de busca global
│
├── tools/
│   └── logger.py                 ← Logger customizado (apenas stderr — stdout é JSON-RPC)
│
├── docs/
│   ├── SESSION_LOG.md            ← Log de sessões de desenvolvimento
│   ├── ARCHITECTURE.md           ← Documentação de arquitetura
│   └── adr/                      ← Architecture Decision Records
│
└── tests/                        ← Testes automatizados
```

---

## Banco de Dados

### Container

```
Nome:  mcp-rust-star-db
Imagem: pgvector/pgvector:pg16
Porta: 5432
```

### Acesso direto

```bash
docker exec -it mcp-rust-star-db psql -U user -d mcp_knowledge
```

### Estrutura das tabelas

Cada projeto tem sua própria tabela com prefixo `rag_`:

```sql
-- Exemplo: projeto 'rust_star' → tabela 'rag_rust_star'
CREATE TABLE rag_rust_star (
    id          UUID PRIMARY KEY,
    content     TEXT,
    embedding   vector(2560),    -- qwen3-embedding:4b = 2560 dims
    source      TEXT,            -- caminho absoluto do arquivo
    project_id  TEXT,
    chunk_hash  TEXT,            -- MD5 do conteúdo (cache)
    metadata    JSONB            -- tags, category, etc.
);

CREATE INDEX ON rag_rust_star USING hnsw (embedding vector_cosine_ops);
```

### Consultas úteis

```sql
-- Quantos chunks por projeto
SELECT project_id, COUNT(*) FROM rag_rust_star GROUP BY project_id;

-- Arquivos indexados
SELECT DISTINCT source FROM rag_rust_star ORDER BY source;

-- Busca por similaridade manual
SELECT source, 1 - (embedding <=> '[...]'::vector) AS score
FROM rag_rust_star
ORDER BY embedding <=> '[...]'::vector
LIMIT 5;

-- Remover projeto específico
DELETE FROM rag_foxot;

-- Ver todas as tabelas RAG
SELECT tablename FROM pg_tables WHERE tablename LIKE 'rag_%';
```

### Pool de Conexões

O `PostgresStore` usa um pool de 1–15 conexões (`psycopg2.pool.SimpleConnectionPool`) com:
- `connect_timeout`: 10 segundos
- `keepalives`: ativado (idle=30s, interval=10s, count=5)
- `autocommit`: ativado por conexão

---

## Otimizações de GPU (8 GB VRAM)

O servidor foi configurado especificamente para funcionar bem em GPUs com 8 GB de VRAM.

### Configurações Ollama aplicadas

| Parâmetro | Valor | Efeito |
|---|---|---|
| `num_ctx` | `32768` | Janela de contexto de 32k tokens |
| `num_gpu` | `-1` | Usa todas as camadas disponíveis na GPU |
| Flash Attention | automático | Reduz uso de VRAM do KV cache em ~40% |
| KV cache quantization | `q8_0` | Reduz KV cache de FP16 para 8-bit |

### Por que 32k de contexto cabe em 8 GB?

Com `qwen3.5:4b` + Flash Attention + KV cache q8_0:
- Pesos do modelo: ~3.4 GB
- KV cache (32k tokens, q8_0): ~1.1 GB
- **Total: ~4.5 GB** — deixa ~3.5 GB livres para o SO e outras apps

Com `qwen3-embedding:4b`:
- Pesos: ~2.7 GB
- Sem KV cache significativo (embed não é autoregressivo)
- **Total: ~2.7 GB**

### O ModelGuard como proteção

Os dois modelos **nunca rodam simultaneamente**. O ModelGuard garante isso via asyncio.Lock FIFO. Se uma busca RAG chegar enquanto o embed está rodando, ela aguarda na fila sem travar o servidor.

### RAM como buffer de contexto

O Ollama usa RAM como armazenamento intermediário quando a VRAM está cheia. Com 16 GB de RAM:
- Camadas que não cabem na VRAM vão para RAM automaticamente
- Lento mas funciona sem crash

### Dicas para melhorar ainda mais

```env
# Para embeddings menores (mais rápido, menos preciso):
EMBEDDING_MODEL=qwen3-embedding:0.6b
EMBEDDING_DIM=1024

# Para modelo menor de RAG (libera mais VRAM):
RAG_MODEL=qwen3:1.7b
```

---

## Solução de Problemas

### Servidor não inicia

**Erro: Python venv não encontrado**
```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

**Erro: Docker não encontrado**
Instale o Docker Desktop e certifique-se de que está no PATH.

**Erro: Ollama não detectado na porta 11434**
Inicie o Ollama: `ollama serve` (ou abra o aplicativo Ollama).

**Erro: PostgreSQL não ficou pronto**
```bash
docker compose down
docker compose up -d
docker logs mcp-rust-star-db
```

### Embed lento ou travado

1. Verifique uso de VRAM: `get_gpu_status()`
2. Descarregue VRAM: `unload_vram()`
3. Cancele e retome: `cancel_embed()` → `batch_index_projects()`
4. Verifique se outro processo está usando a GPU

### Out of Memory (OOM) durante embed

- Reduza o `chunk_size` em `.env` (ex: `CHUNK_SIZE=6000`)
- Ou mude para modelo menor: `EMBEDDING_MODEL=nomic-embed-text`
- Use `unload_vram()` antes de iniciar o embed

### Respostas RAG desatualizadas

Se um arquivo foi editado mas o RAG ainda retorna a versão antiga:

```
batch_index_projects(["nome_do_projeto"], force=True)
```

Isso re-processa todos os arquivos independente do cache MD5.

### Fantasmas no banco (chunks de arquivos deletados)

Ao indexar o projeto completo, a limpeza de fantasmas é automática. Para forçar manualmente:

```
clear_knowledge_base("nome_do_projeto")
batch_index_projects(["nome_do_projeto"])
```

### Dashboard não conecta

```bash
# Verifica se o servidor está rodando
curl http://127.0.0.1:8765/health

# Verifica telemetria
curl http://127.0.0.1:8765/telemetry
```

### Verificar integridade do banco

```bash
docker exec -it mcp-rust-star-db psql -U user -d mcp_knowledge -c "\dt rag_*"
```

---

## Logs

| Arquivo | Conteúdo |
|---|---|
| `logs/mcp_error.log` | Log principal do servidor (erros, info, warnings) |
| `logs/startup.log` | Log de inicialização do `run_server.bat` |
| `logs/dashboard.log` | Log do dashboard Flask |
| `logs/rag_history/index.json` | Índice de cache de respostas RAG |
| `logs/rag_history/<project>/query_*.md` | Respostas RAG salvas como markdown |

O logger usa apenas `stderr` para não corromper o protocolo JSON-RPC que trafega no `stdout`.

---

## Licença

Projeto privado. Todos os direitos reservados — FoxPop / Phantasy.
