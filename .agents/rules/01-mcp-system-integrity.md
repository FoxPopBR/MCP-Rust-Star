---
trigger: model_decision
description: Quando precisar saber mais informações sobre como funciona o sistema do projeto.
---

# Regra 01: Integridade do Sistema e Disciplina Técnica

## 1. Tratamento de Erros e Diagnósticos
Seguindo o padrão de elite do Rust Star, o tratamento de erros em Python deve ser rigoroso e transparente.

### Uso do CustomLogger
- Toda nova funcionalidade deve importar o `logger` de `tools.logger`.
- **Níveis de Log**:
    - `debug()`: Fluxo de dados interno, variáveis e estados temporários.
    - `info()`: Marcos de execução (ex: "Servidor MCP iniciado", "Projeto X registrado").
    - `warning()`: Situações inesperadas mas recuperáveis (ex: "Modelo Ollama demorando a responder").
    - `error()`: Falhas em operações que não derrubam o servidor (ex: "Falha ao indexar arquivo específico").
    - `critical()`: Falhas que impedem o funcionamento de ferramentas essenciais.

### Tracebacks Detalhados
- Utilize `logger.error_with_traceback(e, "nome_da_funcao")` dentro de blocos `except` para garantir que a causa raiz seja documentada no arquivo de log.

---

## 2. Integridade do Protocolo MCP
O servidor MCP é extremamente sensível à integridade da comunicação via STDIO.

- **Isolamento de Saída**: O `stdout` pertence exclusivamente ao protocolo JSON-RPC. Qualquer caractere extra (como newlines ou mensagens de bibliotecas) causa erro de "EOF while parsing a value".
- **Redirecionamento Cirúrgico**: Para garantir a estabilidade, todas as ferramentas MCP devem usar o decorador `mcp_tool_with_logging` que implementa `contextlib.redirect_stdout(sys.stderr)`. Isso força qualquer saída acidental para o canal de erro, preservando o canal de dados.
- **Validação de Retorno**: As ferramentas devem sempre retornar strings amigáveis ou JSON válido.

---

## 3. Padrão de Codificação Pythonic
- **Tipagem**: Use `type hints` em todas as definições de funções para aumentar a robustez do código.
- **Documentação**: Docstrings são obrigatórias em todas as ferramentas MCP, explicando parâmetros e o comportamento esperado.
- **Segurança de Ambiente**: Variáveis sensíveis (caminhos de rede, nomes de modelos) devem vir exclusivamente do arquivo `.env`.

---

## 4. Integridade de Persistência SQL

Com a migração para o **PostgreSQL + pgvector**, a disciplina com os dados foi elevada:
- **Isolamento de Tabelas**: Cada projeto deve ter sua própria tabela (`knowledge_[project_id]`). NUNCA misture dados de projetos diferentes em uma tabela global.
- **Validação de Vetores**: Antes de gravar, o sistema deve garantir que as dimensões do embedding (ex: 4096) batem com a configuração da tabela.
- **Transacionalidade**: Operações massivas devem ser feitas em lotes (batch) para otimizar o I/O do banco.

## 5. Evolução da Base de Conhecimento
- Toda vez que uma "gambiarra" for detectada ou um bug complexo for resolvido, uma nova **Skill** deve ser criada em `.agents/skills/` para documentar o aprendizado e evitar a reincidência.
