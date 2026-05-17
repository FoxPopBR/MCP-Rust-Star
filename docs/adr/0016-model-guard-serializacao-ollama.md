# ADR-0016: ModelGuard — Serialização Global de Operações que Tocam Ollama

Qualquer ferramenta que chame Ollama (embedding, chat RAG, visão) ocupa toda a VRAM disponível enquanto o modelo está carregado. Execuções concorrentes não causam crash mas disputam VRAM, forçando Ollama a fazer swap e degradando performance de forma imprevisível. Decidimos serializar todas essas operações com um único `asyncio.Lock` global gerenciado por um `ModelGuard` singleton.

## Contexto

O servidor é de uso exclusivo single-user (localhost), portanto latência adicional por serialização é aceitável. O problema real é a imprevisibilidade: sem serialização, `ask_knowledge_base` pode iniciar enquanto `batch_index_projects` está no meio de um embedding, e o Ollama divide a VRAM entre os dois modelos (embed + chat), causando:

1. Latência exponencialmente maior (swap de modelo).
2. Possíveis falhas de OOM silenciosas dependendo da GPU.
3. Impossibilidade de rastrear "quem está usando o modelo agora" para fins de observabilidade.

O padrão VRAM Eject (`keep_alive=0`) já libera VRAM após cada uso — o ModelGuard garante que apenas uma operação por vez chega até esse ponto.

## Decisão

Implementar `src/services/model_guard.py` com:

- **Lock global único** (`asyncio.Lock`) — uma operação por vez, FIFO natural do asyncio.
- **Estado observável**: `current_holder` (tool em execução, tipo, início) + `queue` (lista de espera com timestamp de enqueue).
- **`stats()`**: snapshot instantâneo para `/health` e diagnóstico.
- **Integração com EventBus**: emite `model.queued`, `model.acquired`, `model.released` — TelemetryWriter e dashboard consumirão esses eventos na Fase 4.
- **Decorator `@with_model_guard(kind=...)`**: aplica o guard de forma transparente sem alterar a lógica interna das tools.

## Decisão crítica (Revisada): Lock Granular por Arquivo com Lookahead FIFO vs. Lock Global por Batch

A abordagem original de segurar o lock de embedding durante todo o lote (`_batch_embed_worker`) e toda a pasta (`index_directory`) causava travamentos severos: locks contínuos por horas na GPU do usuário e deadlocks de reentrabilidade caso ferramentas internas se chamassem.

Decidimos migrar para uma **Fatia de Concorrência Cooperativa e Granular**:
1. **Locks Granulares por Arquivo**: O lock do `ModelGuard` é adquirido e liberado de forma granular, apenas para cada arquivo individual indexado. Isso permite que uma pergunta RAG prioritária (`ask_knowledge_base`) se intercale de forma cooperativa entre dois arquivos sem ficar travada.
2. **Lookahead FIFO (`peek_next_kind()`)**: O `ModelGuard` implementa lookahead na fila de espera. Ao término de cada arquivo indexado, a rotina espreita o próximo item da fila:
   - Se a fila estiver vazia ou se o próximo `kind` for diferente de `"embed"` (ex: uma pergunta `"chat"` do usuário ou uma imagem `"vision"`), o modelo do Ollama é descarregado proativamente (`unload_models()`) para manter a VRAM limpa (VRAM Eject Pattern).
   - Se o próximo item for outro `"embed"`, a descarga é pulada para reter o modelo na memória da GPU e maximizar o throughput da indexação em lote.

## Causa Raiz e Retratação da Regressão do `auto_unload`
Identificou-se que a regressão original que impulsionou o desenho do lock global por batch foi a desativação acidental do descarregamento automático do Ollama (`auto_unload=False` no `get_embedding()` no commit `73aa752`), fazendo com que o modelo de embedding persistisse na GPU e competisse com as consultas RAG. A restauração do default `auto_unload=True` (Fatia 1) eliminou a necessidade de locks por lote inteiro.

## Tools que recebem o decorator

`index_file`, `index_directory`, `batch_index_projects` (envolve o worker inteiro), `ask_knowledge_base`, `analyze_screenshot`, `index_image`, `retry_failed_files`.

## Alternativas consideradas

- **Lock por tipo de modelo (embed vs. chat)**: permitiria dois embeds paralelos, mas complica a lógica e não há caso de uso — há um único modelo embed e um único modelo chat configurados.
- **Semáforo com N=1**: equivalente ao Lock, sem benefício adicional aqui.
- **Sem serialização (estado atual)**: não escala para cenário multi-cliente HTTP (Fase 1) onde IDE e CLI podem chamar tools simultaneamente.

## Consequências

- Uma tool que usa Ollama aguarda na fila enquanto outra está ativa — tempo de espera visível no `stats()` e nos eventos do bus.
- `batch_index_projects` pode bloquear `ask_knowledge_base` por minutos — aceitável para uso single-user com conhecimento explícito do usuário.
- O endpoint `/health` (Fase 6) pode expor `model_guard.queue_depth` para diagnóstico em tempo real.
