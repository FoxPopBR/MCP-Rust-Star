---
trigger: model_decision
description: Para saber mais sobre Performance RAG e Enriquecimento de Dados
---

# Regra 05: Performance RAG, Enriquecimento e Pós-Processamento de Dados

A qualidade das respostas do assistente depende diretamente da precisão da recuperação (Retrieval), da economia de tokens no contexto e do rigor do pipeline de pós-processamento.

## 1. Enriquecimento de Metadados
Sempre que possível, o sistema deve "enriquecer" os fragmentos com contexto estruturado:
- **Categorização por Caminho**: Utilizar a estrutura de pastas (ex: `/monster/`, `/spells/`) para injetar metadados de categoria.
- **Filtro Semântico**: Durante a busca, as ferramentas RAG devem permitir a passagem de filtros de metadados para reduzir o ruído no espaço vetorial.

## 2. Otimização de Busca e Pós-Processamento (De-duplication & De-overlapping)
O pipeline RAG executa etapas atômicas de pós-processamento antes de entregar os dados brutos ao cliente:
- **Deduplicação Inteligente por Conteúdo**: Remove chunks com conteúdo normalizado idêntico retornados pelo banco vetorial. Mantém apenas a ocorrência com menor distância semântica cossena.
- **Fusão de Chunks Adjacentes (De-overlapping)**: Detecta chunks contíguos de um mesmo arquivo com base no `chunk_index` e remove fisicamente a sobreposição padrão de 1.000 caracteres, fundindo-os em um único bloco de alta legibilidade para poupar até 40% de consumo de tokens desnecessários.
- **Filtro de Ruído Semântico (Locales/Traduções)**: Analisa a query. Se ela não tratar de termos como `locale`, `traduzir`, `langs`, etc., caminhos de arquivos contendo strings de internacionalização recebem uma penalização cossena multiplicadora de `1.5`, movendo arquivos secos de locale para fora da janela útil de resultados.
- **Top-N Contextual**: O número de fragmentos retornados (`n_results`) deve ser ajustado com base na complexidade da pergunta. Perguntas de lore exigem mais contexto do que perguntas sobre uma assinatura de função específica.
- **Threshold de Similaridade**: Descartar resultados com baixa similaridade de cosseno para evitar que o LLM tente "adivinhar" respostas baseado em ruído.

## 3. Gestão de Recursos (VRAM)
- **Descarregamento Proativo**: Após operações intensivas de embedding, o sistema deve SEMPRE solicitar ao Ollama o descarregamento dos modelos (`unload_models`).
- **Paralelismo Seguro**: A indexação massiva deve ser feita de forma a não travar a CPU/GPU do usuário, utilizando batching e pausas controladas se necessário.

---
