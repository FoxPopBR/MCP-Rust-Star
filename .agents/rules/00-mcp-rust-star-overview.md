# Regra 00: Apresentação e Protocolo (MCP Rust Star)

## 1. Visão Geral do Projeto
O **MCP Rust Star Knowledge Server** é um servidor Model Context Protocol (MCP) que fornece uma base de conhecimento RAG (Retrieval-Augmented Generation) para o ecossistema Rust Star. Ele utiliza **Python 3.10+**, **PostgreSQL + pgvector** (Persistência Industrial) e **Ollama** (Local LLM) para gerenciar lore, código e documentação de forma isolada entre projetos.

### Pilares de Engenharia de Elite
- **Soberania do Grilling (Regra 02)**: Nunca codificar sem antes questionar premissas e estados de erro.
- **Diagnóstico Científico (Regra 03)**: Erros são resolvidos via evidência e telemetria, não por palpite.
- **Fatiamento Vertical (Regra 04)**: Entregas incrementais de ponta a ponta com justificativa técnica via ADRs.
- **Isolamento Multi-Projeto**: Gestão estrita de `project_id` para evitar alucinações cruzadas.
- **Resiliência de VRAM**: Protocolos de `unload` proativo de modelos para garantir coexistência com o desenvolvimento local.

---

## 2. Protocolo "Stop & Think"
**ESTA É A REGRA SOBERANA DO PROJETO.**

Antes de qualquer execução técnica, o agente deve:
1.  **Consultar o SESSION_LOG.md**: Ler o diário de sessão para entender onde a última iteração parou.
2.  **Validar o Escopo**: Garantir que as alterações respeitam os limites do `project_id`.
3.  **Sabatina Interna**: Aplicar o "Grilling" para identificar riscos de VRAM e performance do RAG.
4.  **Linguagem Ubíqua**: Traduzir pedidos vagos usando o dicionário do `CONTEXT.md`.

---

## 3. Protocolo de Documentação e Continuidade

### 3.1. Documentação Incremental
- **Proibido**: Resumos genéricos ou simplificações por economia de tokens.
- **Obrigatório**: Documentação técnica densa construída em etapas (ex: `docs/ARCHITECTURE.md`). Se o assunto for complexo, trabalhe em múltiplos turnos para garantir profundidade.

### 3.2. Diário de Sessão (`docs/SESSION_LOG.md`)
- Ao final de cada grande ciclo de trabalho ou antes do encerramento da conversa, o agente **DEVE** atualizar o `SESSION_LOG.md` com fatos técnicos, decisões e o plano para a próxima sessão.

---

## 4. Uso de Skills de Elite

O agente deve utilizar proativamente as **Skills** registradas em `.agents/skills/` para guiar seu comportamento:
- **improve-codebase-architecture**: Para refatorações e documentação de design.
- **diagnose**: Para bugs complexos e problemas de VRAM.
- **triage**: Para gestão de tarefas e débitos técnicos.
- **Aderência**: O sucesso do projeto é medido pela fidelidade a esses padrões e não apenas pela entrega de código funcional.

---

## 3. Diretrizes de Desenvolvimento

### Pythonic Zero Panic
- **Proibido**: Uso de `try/except: pass`.
- **Obrigatório**: Uso do decorador `@logger.log_exception` do `tools.logger` em todas as ferramentas MCP.

### Protocolo de Logging (Atenção Máxima)
- **NUNCA** usar `print()`. O `stdout` é reservado exclusivamente para o protocolo JSON-RPC do MCP.
- **Padrão**: Usar apenas a instância `logger` de `tools.logger`. Saídas direcionadas para `sys.stderr`.
