# ADR 005: RAG local focado estritamente em Busca Semântica de Alta Precisão (Search-Only)

## Status
**Aprovado** (Maio de 2026)

## Contexto
O pipeline original do RAG utilizava uma abordagem híbrida local onde os fragmentos de código recuperados da busca vetorial no PostgreSQL eram passados para um modelo RAG local (`qwen3.5:9b` em chat mode) rodando no Ollama para sintetizar uma resposta e citar fontes.

Isso causava dois grandes problemas:
1. **Contenção e degradação de VRAM:** Rodar o modelo de embedding (5GB) e o modelo de chat (6GB) simultaneamente em uma GPU com 8GB de VRAM forçava o Ollama a mover camadas para a CPU, degradando a performance de inferência e a capacidade lógica do modelo.
2. **Qualidade inferior de raciocínio lógico:** O modelo de 9B local frequentemente gerava respostas conservadoras ou alucinadas (ex: "a base não contém essa informação"), apesar de os fragmentos corretos de código estarem presentes no contexto retornado pela busca.

## Decisão
Decidimos que:
- O RAG local do MCP Rust Star funcionará **exclusivamente no modo "Search-Only" (Modo Raw)**.
- O modelo de chat local (`qwen3.5:9b`) é completamente removido do fluxo principal de ferramentas do MCP (exceto em análises multi-projeto legadas onde a fusão local é exigida).
- As ferramentas MCP de busca (`ask_knowledge_base`, `search_project_knowledge`, `search_all_projects_knowledge`) retornarão os fragmentos brutos das buscas vetoriais, purificados, otimizados e ordenados por distância, diretamente para o modelo chamador (Claude, Gemini, GPT) que possui capacidade lógica muito superior para raciocinar e construir a resposta definitiva para o desenvolvedor.
- Para evitar ruídos e redundâncias, implementamos um pipeline avançado de pós-processamento de chunks no `rag_service.py` compreendendo:
  1. **Penalização Cossena para Locales:** Arquivos de tradução (locales) têm suas distâncias aumentadas por um fator de `1.5` quando a query for sobre lógica de código ou UI, prevenindo poluição semântica.
  2. **Deduplicação de Conteúdo:** Filtro de fragmentos duplicados.
  3. **Fusão de Chunks Adjacentes (De-overlapping):** Fragmentos contíguos do mesmo arquivo são fundidos em um único bloco de código maior usando correspondência de sufixo/prefixo comum, economizando tokens e melhorando a coesão semântica para o modelo chamador.

## Consequências
- **VRAM Livre:** Liberação drástica da memória GPU de 8GB, pois apenas o modelo leve de embedding carrega na memória.
- **Raciocínio de Elite:** O modelo de front-end do usuário (como Claude ou Gemini) agora recebe os fragmentos de código reais e estruturados, conectando conceitos (como saber que `entergame.otui` é a tela de login) perfeitamente.
- **Eficiência de Tokens:** A fusão e deduplicação inteligente remove pedaços redundantes e economiza consumo de contexto na janela de conversação.
