# Diário de Sessão: MCP Rust Star Knowledge Server

Este documento é o registro mestre de transição entre sessões. Ele detalha o estado atual do projeto, marcos alcançados e o planejamento imediato para a continuidade do desenvolvimento.

---

## 🗓️ Sessão: 15/05/2026 - Estabilização e Elite Pipeline

### 1. Principais Conquistas e Fatos
- **Estabilização Crítica do RAG**: Resolvemos os travamentos de VRAM e timeouts do Ollama implementando a **Subdivisão Recursiva** de fragmentos. Agora, se um arquivo falha por ser muito grande, o sistema o divide automaticamente até que o embedding seja possível.
- **Dashboard de Engenharia (Real-Time)**: Substituímos os mocks por um painel real construído com `rich`. O dashboard agora reflete fielmente o estado do `RAGService` (Novos, Cache, Ignorados) e exibe logs coloridos via `stderr`.
- **Início do "Heavy Test" (FoxOT)**: Iniciamos a indexação massiva de 11.000+ arquivos. Em apenas 15 minutos, processamos mais de 1.500 novos arquivos com 0 erros, validando a robustez do motor.
- **Institucionalização Técnica**: Criamos o `docs/ARCHITECTURE.md` (detalhando o sistema em 4 etapas) e o `docs/SUGGESTIONS.md` (backlog de inovações).

### 📔 Diário de Transição de Sessão - MCP Rust Star

- **Última Atualização**: 15/05/2026 16:00
- **Status do Motor**: Indexação de `FoxOT` em andamento (~2.6k+ arquivos).

---

## 1. Estado da Infraestrutura (PostgreSQL)
A migração para persistência industrial foi concluída. O banco de dados agora possui:
- **Tabela `knowledge_foxot`**: Ativa, com índice vetorial pgvector operando em 4096 dimensões (qwen3-embedding).
- **Isolamento**: Verificado. Consultas ao `project_id="Rust Star"` não acessam os fragmentos do `FoxOT`.
- **Integridade**: O `RAGService` está utilizando o padrão de batching para evitar sobrecarga de conexão.

## 2. Telemetria e Monitoramento
- **Dashboard (`dashboard.py`)**: Operacional via `dashboard.bat`. Lê o estado compartilhado de `data/current_indexing.json`.
- **Progresso FoxOT**: Atualmente processando a subpasta `canary-engine\data-otservbr-global\npc`. 
- **Logs de Erro**: O arquivo `logs/mcp_error.log` está limpo (0 erros nas últimas 1.000 iterações).

## 3. Auditoria de Regras e Governança
- **Regra 00**: Atualizada com o protocolo de "Stop & Think" e Diário de Sessão mandatório.
- **Regra 05**: Nova regra criada para formalizar o **Enriquecimento de Metadados** (Categorização por Path).
- **ADR-0005 e 0006**: Criados para documentar a troca de DB e a arquitetura de monitoramento.

## 4. O que falta (Próxima Sessão)
1.  **Validação do FoxOT**: Assim que a indexação NPC terminar, realizar uma pergunta complexa de Lua para testar a precisão do RAG no Postgres.
2.  **Enriquecimento de Metadados**: Implementar o injetor de `category` no `vector_store_postgres.py` baseado nos diretórios (`monster`, `npc`, `spell`).
3.  **Otimização de Busca**: Ajustar o Top-K para 7 em consultas de lore e 3 em consultas de código.

---
**Nota para o Próximo Agente**: Não confie na sua "eficiência natural". Re-leia as regras da `GEMINI.md` sobre superficialidade. Verifique se o Postgres ainda está de pé (`check_ollama_status`) antes de qualquer pergunta.

### 2. Desafios Superados
- **Caminhos Absolutos**: Corrigimos a "falha de visão" do dashboard garantindo que tanto o servidor MCP quanto o script de monitoramento usem caminhos absolutos baseados no root do projeto para acessar os arquivos de estado (`current_indexing.json`).
- **Gestão Proativa de VRAM**: Implementamos a ejeção forçada de modelos do Ollama entre grandes blocos de tarefas, garantindo que a GPU do usuário permaneça livre para outras atividades.

### 3. Estado Atual do Sistema
- **Crawler**: Ativo no projeto `FoxOT`.
- **Persistência**: Operacional via PostgreSQL + pgvector (tabelas isoladas).
- **Dashboard**: Funcional e exibindo dados reais da indexação em background.

---

## 🚀 Planejamento para a Próxima Sessão

### A. Validação do Batch Indexing
- Confirmar a conclusão dos 10k arquivos do FoxOT e verificar se o `batch_progress.json` marcou o projeto como concluído.
- Iniciar a indexação do projeto `Rust Star` (Engine) se ainda não tiver sido concluída.

### B. Implementação de "Metadata Enrichment"
- Conforme registrado em `SUGGESTIONS.md`, implementar a categorização automática por caminho de diretório (ex: monster, spell, engine) para melhorar a precisão do RAG.

### C. Refinamento de Busca (RAG)
- Realizar testes de estresse na busca vetorial agora que a base de dados possui milhares de fragmentos, ajustando os parâmetros de `top-N` se necessário.

---
> [!IMPORTANT]
> **Nota para a Próxima Sessão**: Antes de qualquer ação, consulte este diário e os documentos em `docs/` para manter a integridade da arquitetura alcançada.
