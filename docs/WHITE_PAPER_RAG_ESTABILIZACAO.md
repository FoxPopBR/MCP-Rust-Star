# Whitepaper de Engenharia: Estabilização e Otimização do Sistema RAG (Rust Star / FoxOT / FoxClient)

## 1. Sumário Executivo
Este documento serve como o registro histórico e técnico definitivo da transição do sistema RAG do **MCP Rust Star** para uma arquitetura de alta disponibilidade e resiliência. Através de ciclos intensivos de depuração, superamos falhas críticas de exaustão de VRAM, deadlocks de banco de dados e travamentos silenciosos do motor de inferência Ollama. O resultado é uma infraestrutura capaz de indexar repositórios massivos com recuperação automática de falhas.

---

## 2. Histórico de Incidentes e Diagnóstico Crítico

### 2.1. A Crise do Erro 500 (Ollama Context Overflow)
*   **Problema:** Inicialmente, o sistema utilizava fragmentos de texto sem limites rígidos de tokens, confiando na configuração do Ollama de 16k tokens. 
*   **Falha:** O modelo `qwen3-embedding` apresentava Erro 500 ou travava a GPU ao receber chunks densos que, embora abaixo de 16k caracteres, excediam o limite de tokens reais após a tokenização.
*   **Resolução:** Implementação do **ADR 0004**, fixando o `chunk_size` em 8000 caracteres como barreira de segurança física.

### 2.2. Deadlock do Global Interpreter Lock (GIL) e Threads
*   **Problema:** O servidor MCP (FastMCP) rodava em um loop `asyncio`, enquanto o worker de indexação rodava em uma `threading.Thread` separada.
*   **Falha:** Quando o worker travava em uma chamada de rede (Ollama) ou disco (Postgres), ele segurava o GIL. Como as ferramentas MCP também precisavam do GIL para responder ao usuário, o servidor inteiro entrava em estado de "Congelamento Total".
*   **Resolução:** Introdução de `asyncio.to_thread` para todas as ferramentas e o dashboard de monitoramento externo passivo.

### 2.3. Contenção de I/O de Log (Windows File Lock)
*   **Problema:** O worker de fundo escrevia logs via módulo `logging` padrão para `logs/mcp_error.log`.
*   **Falha:** Ao abrir o log em editores como Bloco de Notas ou ao rodar ferramentas de monitoramento que bloqueavam o arquivo, o Python parava de executar, aguardando o desbloqueio do arquivo para escrever a próxima linha.
*   **Resolução:** Criação do `dashboard.py`, que lê o log de forma não-bloqueante e resiliente a falhas de acesso.

---

## 3. Arquitetura de Resiliência (Camada por Camada)

### 3.1. Camada de Inferência (Ollama)
O `OllamaClient` foi blindado com as seguintes proteções:
*   **Timeout Transacional:** Cada chamada agora tem um cronômetro. Se o Ollama não responder em 60s (Embedding) ou 90s (Chat), a conexão é abortada para não travar o worker.
*   **Contexto Forçado (12k):** Em vez de confiar no estado global do Ollama, passamos `num_ctx: 12288` em cada requisição, garantindo previsibilidade de uso de VRAM (~5.9GB).
*   **Protocolo de Ejeção Imediata:** A função `_unload_model` foi otimizada para enviar `keep_alive: 0` imediatamente após a última tarefa, liberando a GPU para outros processos (como o seu jogo ou editor).

### 3.2. Camada de Inteligência de Chunks (RAGService)
Implementamos a técnica de **"Fallback Splitting"**:
1.  O sistema tenta indexar um fragmento de 8000 caracteres.
2.  Se houver erro (timeout ou sobrecarga), o sistema captura a exceção.
3.  O fragmento é automaticamente subdividido em 4 pedaços de 2000 caracteres.
4.  Esses pedaços são indexados individualmente, garantindo que o progresso continue mesmo em arquivos JSON altamente estruturados.

### 3.3. Camada de Banco de Dados (PostgreSQL)
A transição do ChromaDB (que sofria com corrupção de arquivos em crashes) para o PostgreSQL trouxe:
*   **Connection Pool:** Uso do `psycopg2.pool`, permitindo múltiplas conexões simultâneas (até 15). Isso isola o tráfego do indexador do tráfego de consulta do usuário.
*   **Tabelas Dinâmicas:** Separação física por `project_id` via esquemas, permitindo que a limpeza de um projeto (ex: FoxClient) não afete os dados do Rust Star.

---

## 4. Guia de Operação e Manutenção

### 4.1. Como Monitorar sem Travar
*   **NUNCA** use ferramentas MCP de status (`get_embed_status`) repetidamente se o processo estiver pesado.
*   **USE SEMPRE** o `dashboard.bat`. Ele foi desenhado para ser "invisível" ao sistema, lendo apenas o que já foi escrito no disco.

### 4.2. Recuperação de Desastres
1.  Se o processo parar e a VRAM não baixar: Verifique o dashboard. Se o log parou há mais de 2 minutos, faça um `/mcp reload`.
2.  O sistema possui **Retomada Automática**: Ao reiniciar o embed, ele lerá o `data/batch_progress.json` e o cache MD5 no Postgres para pular o que já foi feito, voltando direto ao ponto da falha.

---

## 5. Evolução Futura: Roteiro para Estabilidade 100%

### Fase 1: Isolamento de Processos (Multiprocessing) - [PENDENTE]
Migrar de Threads para Processos reais. Isso garantirá que se o worker de indexação tiver um "Segmentation Fault" ou travamento de CPU, o servidor MCP nem sentirá o impacto.

### Fase 2: Watchdog Ativo - [PENDENTE]
Um monitor interno que reinicia o worker se ele ficar em silêncio por mais de 5 minutos, tornando o sistema "Self-Healing" (Auto-Cura).

### Fase 3: Sanitização Avançada de Dados
Filtros específicos para arquivos JSON de "data/things" que comprimem o texto antes de enviar para o Ollama, economizando tokens e tempo.

---
**Documento finalizado em:** 15 de Maio de 2026  
**Status do Ecossistema:** Estabilizado com Resiliência Ativa.
