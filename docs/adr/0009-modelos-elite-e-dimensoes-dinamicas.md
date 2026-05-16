# ADR 0009: Migração para Modelos de Elite (8B/9B) e Dimensões Dinâmicas

## Status
Aceito

## Contexto
Para elevar o nível de raciocínio técnico e precisão da busca semântica, decidimos migrar os modelos base do servidor MCP de 4B para 8B (Embedding) e 9B (Chat/RAG).

### Desafios Identificados
1.  **Incompatibilidade de Vetores**: O modelo `qwen3-embedding:8b` gera vetores de 4096 dimensões, enquanto o modelo anterior gerava 2560. O banco de dados Postgres/pgvector exige que a dimensão seja definida na criação da tabela.
2.  **Limitação de VRAM**: Com 8GB de VRAM, carregar modelos maiores exige um controle rigoroso da janela de contexto (fixada em 12.288 tokens) e ejeção agressiva de modelos (`keep_alive=0`).

## Decisão
1.  **Modelo de Embedding**: `qwen3-embedding:8b` (4096 dimensões).
2.  **Modelo de Chat/RAG**: `qwen3.5:9b` (com foco em lógica de programação).
3.  **Configuração Dinâmica**: Introduzida a variável `EMBEDDING_DIM` no `.env` e refatorado o `PostgresStore` para criar tabelas baseadas nessa variável, eliminando valores "hardcoded".
4.  **Reset de Integridade**: Executado um *Full Wipe* do banco de dados para garantir que todos os vetores na base pertençam à mesma arquitetura (8B).

## Consequências
*   **Positivas**:
    *   Busca semântica muito mais precisa para termos técnicos complexos (C++, Rust, Lua).
    *   Raciocínio superior do modelo 9B para síntese de código.
    *   Flexibilidade para futuros upgrades de modelos apenas alterando o `.env`.
*   **Negativas**:
    *   Tempo de indexação inicial aumentado devido ao tamanho do modelo.
    *   Necessidade de resetar o banco em caso de troca de arquitetura de modelo.

## Notas de Implementação
*   O campo `embedding` no SQL agora utiliza a sintaxe `vector({self.embedding_dim})`.
*   O pipeline de indexação detecta a mudança e exige um reset manual ou automatizado da base para evitar erros de consistência.
