# ADR 0003: Estratégia de Fatiamento (Chunking) e Expansão de Contexto

## Status
Aceito

## Contexto
Com o crescimento da base de conhecimento e a necessidade de indexar documentos técnicos extensos (código-fonte, lore detalhada), o sistema anterior de "arquivo único por embedding" tornou-se insuficiente. O modelo `qwen3-embedding:4b`, apesar de potente, possui limites de janela que, se excedidos, resultam em perda de informação (truncamento). Além disso, o usuário solicitou a exploração da capacidade nativa de contexto longo dos modelos Qwen.

## Decisões
1.  **Expansão para 16k**: Configuramos a janela de contexto (`num_ctx`) para 16.384 tokens tanto para o processo de embedding quanto para a geração de resposta (RAG).
2.  **Recursive Character Text Splitting**: Implementamos o fatiamento recursivo utilizando a biblioteca `langchain-text-splitters`.
    *   **Chunk Size**: 12.000 caracteres (aprox. 3k-4k tokens), garantindo margem de segurança dentro dos 16k.
    *   **Chunk Overlap**: 1.000 caracteres, preservando a continuidade semântica entre fragmentos vizinhos.
    *   **Separadores**: Ordem de prioridade: `\n\n` (parágrafos), `\n` (linhas), ` ` (palavras).
3.  **Aumento de Top-K**: A busca agora recupera os 5 fragmentos mais relevantes (`n_results=5`), aproveitando a janela expandida do LLM para uma síntese mais rica.
4.  **Metadados de Fragmentação**: Adicionamos `chunk_index` e `total_chunks` aos metadados de cada vetor para permitir rastreabilidade e reconstrução lógica se necessário.

## Consequências
- **Precisão**: Documentos longos são agora indexados integralmente, sem truncamento.
- **Raciocínio**: O modelo de resposta (`qwen3.5:4b`) recebe uma base de fatos muito mais ampla para formular respostas.
- **Escalabilidade**: O sistema agora suporta arquivos de qualquer tamanho através da fragmentação automática.
