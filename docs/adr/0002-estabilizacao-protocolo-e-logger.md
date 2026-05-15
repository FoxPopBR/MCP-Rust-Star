# ADR 0002: Estabilização do Protocolo MCP e Saneamento do Logger

## Status
Proposto

## Contexto
O servidor MCP Rust Star enfrentou falhas críticas de estabilidade, manifestadas como erros de `Invalid JSON: EOF while parsing a value` e falhas de inicialização devido a `IndentationError` no módulo de log.

### Problemas Identificados:
1.  **Contaminação do stdout**: Bibliotecas externas e `prints` acidentais enviavam caracteres para o canal de dados do protocolo MCP (stdout), corrompendo as mensagens JSON-RPC.
2.  **Erros de Sintaxe no Logger**: O arquivo `tools/logger.py` apresentava inconsistências de indentação que impediam a carga do servidor.
3.  **Falhas de Importação**: O contexto de execução de ferramentas MCP às vezes falhava em localizar pacotes locais devido a caminhos mal configurados ou erros de sintaxe em cascata.

## Decisões
1.  **Redirecionamento Cirúrgico**: Implementar o decorador `mcp_tool_with_logging` que utiliza `contextlib.redirect_stdout(sys.stderr)` para isolar qualquer saída de terminal durante a execução de ferramentas.
2.  **Saneamento do Logger**: Reescrita completa do `tools/logger.py` com indentação estrita de 4 espaços, sem caracteres TAB, e verificação rigorosa de escopo para os decoradores `log_exception`.
3.  **Centralização de Logs**: Todos os logs do sistema são direcionados para `sys.stderr` e para o arquivo persistente `logs/mcp_error.log`.
4.  **Isolamento de Erros**: O tratamento de exceções agora captura o erro, documenta o traceback completo no log e retorna uma mensagem amigável para o cliente MCP, evitando a queda do servidor.

## Consequências
- **Estabilidade**: O servidor MCP torna-se resiliente a `prints` de bibliotecas e erros internos, nunca quebrando o protocolo JSON-RPC.
- **Auditabilidade**: Tracebacks completos são armazenados, permitindo diagnóstico disciplinado (Regra 03) sem poluir o terminal do usuário.
- **Integridade**: A estrutura do projeto volta a ser consistente, permitindo a correta indexação e busca via RAG.
