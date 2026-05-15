# Servidor de Conhecimento MCP Rust Star - Instruções do Workspace

Este projeto é um servidor Model Context Protocol (MCP) que fornece uma base de conhecimento RAG (Retrieval-Augmented Generation) isolada para múltiplos projetos.

## Visão Geral do Projeto

*   **Propósito**: Um servidor de conhecimento para indexar e consultar informações (lore, código, docs) para projetos como Rust Star, FoxOT e FoxClient.
*   **Tecnologias**:
    *   **Linguagem**: Python 3.10+
    *   **Framework MCP**: `FastMCP`
    *   **Banco Vetorial**: `PostgreSQL` + `pgvector` (Persistência Industrial em Docker)
    *   **LLM/Embeddings**: `Ollama` (Local)
    *   **Modelos**:
        *   Embedding: `qwen3-embedding:4b`
        *   RAG/Vision: `qwen3.5:4b`

## Arquitetura e Isolamento de Projetos

O servidor suporta **Isolamento Multi-Projeto**. Cada documento indexado é marcado com um `project_id`. As consultas podem ser restritas a um projeto específico ou executadas globalmente.

*   `src/main.py`: Ponto de entrada. Registra ferramentas MCP e gerencia o registro de projetos.
*   `src/services/rag_service.py`: Orquestra o pipeline RAG.
*   `src/ollama_client.py`: Lida com a comunicação com a API local do Ollama.
*   `src/vector_store.py`: Abstração para ChromaDB com filtragem por metadados.
*   `tools/logger.py`: Sistema de log de alta integridade (logs para `stderr` e `logs/mcp_error.log`).
*   `.agents/`: Contém **Regras** (`rules/`) e **Skills** (`skills/`) que governam o comportamento da IA.

## Mandatos e Regras Principais

Consulte `.agents/rules/` para detalhes completos:
*   **Regra 00 (Passo Zero - Protocolo Anti-Minimalismo)**: É PROIBIDO operar em modo de economia de tokens ou fornecer resumos superficiais. Antes de qualquer tarefa, o agente DEVE consultar o `ai-behavior-log` e os KIs de comportamento. Toda análise deve ser um "Deep Dive" técnico, utilizando Skills de arquitetura ou diagnóstico proativamente.
*   **Regra 01 (Integridade)**: Tratamento rigoroso de erros e logs via `CustomLogger`.
*   **Regra 06 (Arquitetura Limpa)**: Separação estrita entre camadas de Interface, Serviço e Persistência.
*   **Regra 07 (ADRs e Diagnóstico)**: Uso de Architecture Decision Records e diagnósticos disciplinados.

## Ferramentas MCP

*   `register_project(project_id, path)`: Registra um novo workspace.
*   `index_file(path)`: Identifica o projeto e indexa um arquivo automaticamente.
*   `index_directory(path, extension)`: Indexa uma pasta inteira mapeando os projetos pelo caminho.
*   `index_image(path)`: Dispara manualmente a visão multimodal (qwen3.5) para descrever e indexar screenshots/diagramas.
*   `get_server_settings()`: Retorna os filtros ativos, extensões ignoradas e status da visão automática.
*   `update_server_settings(ignored_extensions, auto_index_images, chunk_size, n_results)`: Altera as configurações do servidor em tempo real.
*   `ask_knowledge_base(question, project_id=None)`: Consulta contextual com isolamento.
*   `ask_rust_star(question)`: Atalho para o projeto principal.
*   `clear_knowledge_base(project_id=None)`: Exclusão direcionada ou total.
*   `check_ollama_status()`: Diagnóstico dos modelos locais.
*   `unload_vram()`: Libera a memória de vídeo (VRAM) descarregando os modelos do Ollama.

## Padrões de Desenvolvimento e Configurações de Elite

*   **Contexto**: Janela de **12.288 tokens** (otimizada para equilíbrio de VRAM).
*   **Fatiamento (Chunking)**: Uso de `RecursiveCharacterTextSplitter` com 12.000 caracteres de tamanho e 1.000 de sobreposição.
*   **Logging**: NUNCA use `print()` para logs. Use `logger` (de `tools.logger`). O `stdout` é exclusivo para JSON-RPC; logs e erros vão para o `stderr`.
*   **Diagnóstico**: Todas as ferramentas MCP devem ser decoradas com `@mcp_tool_with_logging`.
*   **Identificação de Projeto**: O pipeline identifica automaticamente o projeto com base no caminho do arquivo antes de gerar o embedding.
