# Sugestões para Análise e Implementação

Este documento serve como um repositório de ideias e melhorias arquiteturais para o **MCP Rust Star Knowledge Server**. O objetivo é registrar insights durante o desenvolvimento para implementação futura.

---

## 1. Enriquecimento de Metadados por Caminho (Categorização Automática)
- **Status**: 💡 Sugerido
- **Descrição**: Durante a fase de crawling, identificar a categoria do arquivo com base na estrutura de diretórios (ex: `/monster/`, `/spells/`, `/lib/`).
- **Impacto**: Melhora drasticamente a precisão do RAG ao permitir filtros específicos (ex: "Procure o loot apenas em arquivos da categoria 'monster'").
- **Complexidade**: Baixa/Média. Requer atualização no `RAGService` e na tabela do PostgreSQL para incluir a coluna `category`.

## 2. Chunking Semântico via AST (Abstract Syntax Tree)
- **Status**: 💡 Sugerido
- **Descrição**: Substituir o fatiamento por contagem de caracteres por um parser real (como Tree-sitter) para linguagens como Lua e C++.
- **Impacto**: Garante que funções e classes nunca sejam cortadas ao meio, preservando a integridade lógica de cada fragmento enviado ao LLM.
- **Complexidade**: Alta. Requer integração com parsers de linguagem no Python.

## 3. Worker de Indexação via Multiprocessing
- **Status**: 💡 Sugerido
- **Descrição**: Mover o loop de indexação de uma Thread para um processo separado (`multiprocessing`).
- **Impacto**: Garante isolamento total do GIL (Global Interpreter Lock) do Python, evitando que o servidor MCP fique lento ou pare de responder durante indexações massivas.
- **Complexidade**: Média. Requer gestão de IPC (Inter-Process Communication) para o dashboard.

---
