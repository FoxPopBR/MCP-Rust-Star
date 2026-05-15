# Relatório de Diagnóstico Técnico: Instabilidade no Processo de Indexação

## 1. Situação Atual
O sistema de indexação RAG do **MCP Rust Star** apresenta interrupções intermitentes durante o processamento de grandes volumes de dados (projetos FoxClient, FoxOT, etc.). O processo "para" silenciosamente, mantendo a VRAM ocupada mas sem progresso visível nos logs ou na GPU.

## 2. Problemas Identificados

### 2.1. Deadlock de I/O e Log
- **Sintoma:** O dashboard e o editor de texto param de atualizar, e as ferramentas MCP ficam em "hang".
- **Causa:** O worker de background tenta escrever no log enquanto ferramentas de leitura (como `get_embed_status`) ou processos externos (editores/dashboard) bloqueiam o arquivo no Windows. O Python trava esperando a liberação do arquivo.

### 2.2. Exaustão de Contexto e Timeout do Ollama
- **Sintoma:** Travamento específico em arquivos JSON densos (ex: `proficiencies.json`).
- **Causa:** Fragmentos de 8000 caracteres geram muitos tokens, causando latência extrema ou travamento interno no Ollama. O driver do Ollama para Python não tinha timeout explícito, resultando em espera infinita da thread.

### 2.3. Contenção de Conexão no Postgres
- **Sintoma:** Travamento do servidor MCP ao tentar consultar o status.
- **Causa:** O worker de background ocupava a única conexão disponível no banco durante transações longas, impedindo que qualquer outra ferramenta MCP funcionasse.

## 3. Ações Tomadas (Implementadas)

| Funcionalidade | Descrição | Objetivo |
| :--- | :--- | :--- |
| **Pool de Conexões** | Substituído conexão única por `SimpleConnectionPool` (15 conexões). | Eliminar contenção de DB. |
| **Timeout de API** | Adicionado timeout de 60s/90s nas chamadas ao Ollama. | Evitar travamento por rede/modelo. |
| **Fallback Splitting** | Se um chunk falha, o sistema o quebra em 4 sub-chunks menores. | Superar arquivos JSON densos. |
| **Heartbeat & Dash** | Criado `dashboard.py` e logs de progresso granulares. | Monitoramento não-bloqueante. |
| **Limitação de VRAM** | Fixado contexto em 12k tokens (12288). | Estabilizar consumo de GPU. |

## 4. Próximos Passos e Estratégia de Resolução

1.  **Isolamento de Processo (Multiprocessing):** Mover o worker de indexação para um processo Python separado (`Process` em vez de `Thread`) para que um travamento na indexação não congele o loop de eventos do servidor MCP.
2.  **Sistema de Queue Persistente:** Implementar uma fila real de tarefas para que o processo possa ser retomado exatamente do ponto onde parou, mesmo após um crash.
3.  **Sanitização de JSON:** Adicionar um pré-processador para arquivos JSON de dados que remova redundâncias antes do embedding.

---
**Data:** 2026-05-15  
**Status:** Em fase de estabilização de infraestrutura.
