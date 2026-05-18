# Rust Star MCP Knowledge Server

Servidor MCP de base de conhecimento RAG para os projetos **Rust Star**, **FoxOT** e **FoxClient**. Utiliza **Ollama** local para embeddings e geração de texto, e **PostgreSQL + pgvector** para armazenamento vetorial isolado por projeto.

## Requisitos

- Python 3.10+
- [Ollama](https://ollama.com/) rodando localmente.
- Docker (para o container PostgreSQL + pgvector).
- Modelos baixados no Ollama:
  - `ollama pull qwen3-embedding:8b`
  - `ollama pull qwen3.5:9b`

## Instalação

1. Suba o banco de dados:
   ```bash
   docker compose up -d
   ```
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Verifique o arquivo `.env` para garantir que as URLs e nomes de modelos estão corretos.

## Uso do Servidor MCP

Para rodar o servidor:
```bat
run_server.bat
```

### Ferramentas de Busca

| Ferramenta | Descrição |
|---|---|
| `search_project_knowledge(project_id, question)` | **Principal.** Busca isolada e rápida em um projeto específico. |
| `search_all_projects_knowledge(question)` | Busca em todos os projetos (lenta). |
| `cross_project_analysis(searches_json, analysis_prompt)` | Análise cruzada entre projetos com fila sequencial. |
| `ask_knowledge_base(question, project_id)` | Busca RAG genérica (compatibilidade). |

### Outras Ferramentas

- **`register_project(project_id, path)`** — Registra uma pasta como projeto.
- **`batch_index_projects()`** — Indexa todos os projetos registrados.
- **`index_file(path)`** / **`index_directory(path)`** — Indexa arquivo ou pasta.
- **`list_indexed_sources(project_id)`** — Lista arquivos indexados.
- **`clear_knowledge_base(project_id)`** — Apaga memória de um projeto.
- **`check_ollama_status()`** — Verifica conexão com Ollama.

## Estrutura do Projeto

- `src/main.py`: Ponto de entrada e definição de ferramentas MCP.
- `src/ollama_client.py`: Comunicação com a API do Ollama.
- `src/vector_store_postgres.py`: Armazenamento vetorial PostgreSQL + pgvector (tabelas prefixo `rag_`).
- `src/services/rag_service.py`: Lógica principal do pipeline RAG.
- `docker-compose.yml`: Container PostgreSQL + pgvector.
