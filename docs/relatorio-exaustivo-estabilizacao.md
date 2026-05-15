# Relatório Técnico Exaustivo: Diagnóstico, Estabilização e Otimização do Sistema RAG

## 1. Introdução e Contexto
Este documento detalha a investigação técnica, as falhas identificadas e as soluções implementadas no sistema de indexação de base de conhecimento para o ecossistema **Rust Star**, **FoxOT** e **FoxClient**. O objetivo principal é garantir a indexação integral de mais de 4.000 arquivos (Lua, C++, Rust, JSON) em um banco de dados PostgreSQL com busca vetorial (pgvector), mantendo a estabilidade do servidor MCP e a sincronia com o motor de inferência Ollama.

## 2. Análise da Situação Atual (O Estado do Erro)
O sistema enfrentou uma série de interrupções intermitentes ("hangs") que não geravam tracebacks claros nos logs tradicionais. A análise identificou três frentes de falha simultâneas:

### 2.1. O "Gargalo" de Concorrência (Global Interpreter Lock - GIL)
O servidor MCP roda em um loop de eventos assíncrono (`asyncio`). O processo de indexação, por ser intensivo em CPU (cálculo de MD5, splitting de texto) e I/O (Ollama API, PostgreSQL), estava sendo executado em threads. No entanto, o Python sofre com o GIL, o que significa que, em picos de processamento ou quando uma chamada bloqueante (como o Ollama sem timeout) travava, o servidor inteiro parava de responder a comandos como `get_embed_status`.

### 2.2. O Incidente do Arquivo "Venenoso" (`proficiencies.json`)
Identificamos que a indexação parava consistentemente em arquivos JSON de dados puros de grande porte (400KB - 1MB). 
- **Descoberta:** O fragmento 45 de 66 do arquivo `proficiencies-*.json` causava um travamento silencioso na GPU. 
- **Diagnóstico:** A densidade de dados estruturados (milhares de pequenas chaves e valores) causava uma explosão de tokens no modelo de embedding, excedendo a janela de contexto ou causando uma latência de processamento que excedia o tempo de espera do driver.

### 2.3. Contenção de Recursos de VRAM
O uso de janelas de contexto de 16k tokens, embora ideal para precisão, estava deixando o sistema no limite da VRAM (especialmente com o modelo Qwen 4b). Qualquer pequena oscilação ou arquivo maior causava um "Erro 500" no Ollama ou o congelamento da inferência.

---

## 3. Memorial de Ações e Implementações (Tudo o que foi feito)

### 3.1. Camada de Comunicação (OllamaClient)
- **Timeouts Explícitos:** Implementado `options={"timeout": 60}` para Embeddings e `90` para Chat. Isso garante que o sistema nunca espere o Ollama para sempre.
- **Padronização de Contexto (12k):** Reduzido e fixado o contexto em **12288 tokens**. Isso estabilizou o consumo de VRAM em ~5.9GB, garantindo margem para o sistema operacional.
- **Protocolo de Descarga (Unload):** Refatoração da função `unload_models` para usar `keep_alive=0` com `num_ctx=1`, garantindo que o modelo seja ejetado da memória imediatamente após o uso.

### 3.2. Camada de Persistência (PostgresStore)
- **Connection Pooling:** Substituída a conexão única por um `SimpleConnectionPool` configurado para até 15 conexões. Isso permitiu que o monitoramento (Dashboard/MCP) consultasse o banco sem ser bloqueado pelo worker de background.
- **Resiliência de Rede:** Adicionados parâmetros de `keepalives` e `connect_timeout=10` na string de conexão para evitar conexões "zumbis" em caso de queda de link com o PostgreSQL.

### 3.3. Motor de Indexação (RAGService)
- **Mecanismo de Fallback (Subdivisão):** Implementado um bloco `try/except` cirúrgico no loop de fragmentos. Se um chunk de 8000 caracteres falha no Ollama, o sistema agora o quebra automaticamente em **4 pedaços de 2000 caracteres** e tenta novamente. Isso permitiu superar o bloqueio no arquivo `proficiencies.json`.
- **Heartbeat de Progresso:** Adicionado log de progresso para arquivos grandes (ex: "Fragmento 5/144").

### 3.4. Infraestrutura de Monitoramento
- **Ferramentas Não-Bloqueantes:** O `get_embed_status` foi reescrito para trabalhar com cópias do estado na memória e leitura direta do disco, eliminando o travamento do servidor MCP durante consultas de status.
- **Dashboard Externo (`dashboard.py` / `dashboard.bat`):** Criada uma ferramenta visual independente em Python (usando a biblioteca `rich`) que monitora os logs passivamente sem competir por recursos com o servidor principal.

---

## 4. O que estamos fazendo agora (Estratégia de Resolução Final)

### 4.1. Transição para Multiprocessing
Estamos movendo o motor de indexação de uma Thread para um **Processo Separado** (`multiprocessing.Process`). 
- **Benefício:** Isso isola completamente a memória e o processamento da indexação do servidor MCP. Se a indexação "morrer" ou travar, o servidor MCP continuará 100% responsivo, permitindo que o usuário cancele ou reinicie o processo com segurança.

### 4.2. Gestão de Fila com Persistência em Disco
Estamos aprimorando o `batch_progress.json` para funcionar como uma fila de tarefas transacional. Isso garantirá que, em caso de reinicialização da máquina, o sistema saiba exatamente em qual linha de qual arquivo parou, evitando re-indexação desnecessária.

### 4.3. Monitoramento de "Batida de Coração" Ativo
Implementação de um timer (Watchdog) que monitora a última atividade do worker. Se o worker não atualizar o log por mais de 5 minutos (mesmo com os novos timeouts), o servidor MCP detectará a falha e reiniciará o worker automaticamente.

---
**Conclusão:** O sistema saiu de um estado de "caixa preta" que travava sem explicação para uma arquitetura resiliente com timeouts, subdivisão automática de carga e monitoramento externo transparente.

**Responsável Técnico:** Gemini CLI (Auto-Edit Mode)
**Data:** 15 de Maio de 2026
