# Regra 00: Apresentação e Protocolo (MCP Rust Star)

## 1. Visão Geral do Projeto
O **MCP Rust Star Knowledge Server** é um servidor Model Context Protocol (MCP) que fornece uma base de conhecimento RAG (Retrieval-Augmented Generation) para o ecossistema Rust Star. Ele utiliza **Python**, **ChromaDB** e **Ollama** para gerenciar lore, código e documentação de forma isolada entre projetos.

### Pilares de Engenharia de Elite
- **Soberania do Grilling (Regra 02)**: Nunca codificar sem antes questionar premissas e estados de erro.
- **Diagnóstico Científico (Regra 03)**: Erros são resolvidos via evidência e telemetria, não por palpite.
- **Fatiamento Vertical (Regra 04)**: Entregas incrementais de ponta a ponta com justificativa técnica via ADRs.
- **Isolamento Multi-Projeto**: Gestão estrita de `project_id` para evitar alucinações cruzadas entre *Rust Star*, *FoxOT* e *FoxClient*.

---

## 2. Protocolo "Stop & Think"
**ESTA É A REGRA SOBERANA DO PROJETO.**

Antes de qualquer execução técnica, o agente deve:
1.  **Validar o Escopo**: Garantir que as alterações respeitam os limites do `project_id`.
2.  **Sabatina Interna**: Aplicar o "Grilling" para identificar riscos de VRAM e performance do RAG.
3.  **Linguagem Ubíqua**: Traduzir pedidos vagos usando o dicionário do `CONTEXT.md`.

---

## 3. Diretrizes de Desenvolvimento

### Pythonic Zero Panic
- **Proibido**: Uso de `try/except: pass`.
- **Obrigatório**: Uso do decorador `@logger.log_exception` do `tools.logger` em todas as ferramentas MCP.

### Protocolo de Logging (Atenção Máxima)
- **NUNCA** usar `print()`. O `stdout` é reservado exclusivamente para o protocolo JSON-RPC do MCP.
- **Padrão**: Usar apenas a instância `logger` de `tools.logger`. Saídas direcionadas para `sys.stderr`.
