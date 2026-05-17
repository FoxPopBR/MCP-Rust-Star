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

## Decisão crítica: lock durante batch inteiro vs. entre arquivos

`batch_index_projects` segura o lock **durante todo o batch**, não libera entre arquivos. Liberar entre arquivos abriria janela para `ask_knowledge_base` se intercalar entre dois arquivos do mesmo projeto, carregando o modelo de chat enquanto o modelo de embed ainda está "quente" no Ollama — violando o VRAM Eject Pattern. Consistência vale mais que throughput de interleaving nesse contexto single-user.

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
