# Regra 05: Performance RAG e Enriquecimento de Dados

A qualidade das respostas do assistente depende diretamente da precisão da recuperação (Retrieval) e da performance do pipeline de dados.

## 1. Enriquecimento de Metadados
Sempre que possível, o sistema deve "enriquecer" os fragmentos com contexto estruturado:
- **Categorização por Caminho**: Utilizar a estrutura de pastas (ex: `/monster/`, `/spells/`) para injetar metadados de categoria.
- **Filtro Semântico**: Durante a busca, as ferramentas RAG devem permitir a passagem de filtros de metadados para reduzir o ruído no espaço vetorial.

## 2. Otimização de Busca
- **Top-N Contextual**: O número de fragmentos retornados (`n_results`) deve ser ajustado com base na complexidade da pergunta. Perguntas de lore exigem mais contexto do que perguntas sobre uma assinatura de função específica.
- **Threshold de Similaridade**: Descartar resultados com baixa similaridade de cosseno para evitar que o LLM tente "adivinhar" respostas baseado em ruído.

## 3. Gestão de Recursos (VRAM)
- **Descarregamento Proativo**: Após operações intensivas de embedding, o sistema deve SEMPRE solicitar ao Ollama o descarregamento dos modelos (`unload_models`).
- **Paralelismo Seguro**: A indexação massiva deve ser feita de forma a não travar a CPU/GPU do usuário, utilizando batching e pausas controladas se necessário.

---
