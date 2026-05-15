# ADR-0007: Categorização Híbrida de Metadados no Pipeline RAG

## Status
Aceito (Implementado)

## Contexto
O servidor de conhecimento MCP Rust Star lida com projetos de naturezas distintas:
1. **FoxOT**: Baseado em Lua, com milhares de arquivos de dados (NPCs, Monstros, Spells).
2. **FoxClient**: Módulos de interface e assets.
3. **Rust Star Engine**: Código-fonte de baixo nível (Rust), protocolos e lógica de renderização.

A busca semântica pura (vetorial) às vezes mistura conceitos (ex: buscar "damage" retornava spells de Lua e fórmulas de dano da Engine Rust indiscriminadamente). Precisávamos de um sistema de classificação para permitir filtragem granular.

## Decisões
1. **Esquema de Banco**: Adição das colunas `category` (TEXT) e `tags` (JSONB) na tabela do PostgreSQL.
2. **Lógica Híbrida**:
   - **Elite Mapping**: Mapeamento fixo baseado em substrings do caminho (ex: `/npc/` -> `npc`).
   - **Dynamic Fallback**: Uso da pasta pai imediata como categoria caso não haja match de elite.
   - **Tag Extraction**: Extração das últimas 5 partes do caminho do arquivo como tags semânticas.
3. **Pipeline de Ingestão**: O `RAGService` agora calcula esses metadados em tempo real antes de persistir os fragmentos.
4. **Retrofit**: Criação de scripts de migração para atualizar registros existentes sem necessidade de re-indexação completa (economia de VRAM e tempo).

## Consequências
- **Positivas**:
  - Busca RAG mais precisa através de filtragem por metadados.
  - Melhor contextualização para o LLM (o sistema pode informar a categoria do fragmento).
  - Facilidade de auditoria e estatísticas (ex: saber quantos fragmentos de "engine" existem vs "npc").
- **Negativas**:
  - Pequeno overhead no tempo de indexação para o cálculo das categorias.
  - Dependência da estrutura de pastas para classificação automática.

## Referências
- `src/services/rag_service.py` (`_get_category`, `_get_tags`)
- `src/vector_store_postgres.py` (Update schema)
- `scratch/migrate_categories.py` (Migration script)
