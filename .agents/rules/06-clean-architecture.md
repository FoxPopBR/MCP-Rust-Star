---
trigger: model_decision
description: Como a arquitetura do projeto funciona e praticas adotadas, se mantenha no padrão de geração de código do projeto
globs: A
---

# Regra 06: Arquitetura Limpa e Separação de Responsabilidades

Para garantir que o MCP Rust Star seja escalável e fácil de manter, seguimos uma arquitetura desacoplada.

## 1. Camadas do Sistema

### Camada de Interface (MCP Server) - `src/main.py`
- **Responsabilidade**: Definir ferramentas MCP e lidar com a comunicação via STDIO.
- **Regra**: Esta camada não deve conter lógica de negócio pesada ou manipulação direta do banco de dados vetorial. Ela deve apenas chamar os serviços apropriados.

### Camada de Serviço (RAG Service) - `src/services/rag_service.py`
- **Responsabilidade**: Orquestrar o pipeline de RAG (embeddings, busca, geração).
- **Regra**: Deve ser independente da interface. Se decidirmos trocar o MCP por uma API REST no futuro, esta camada deve permanecer intocada.

### Camada de Persistência (Vector Store) - `src/vector_store_postgres.py`
- **Responsabilidade**: Abstrair o PostgreSQL e operações de persistência de projetos.
- **Regra**: Nenhuma outra camada deve conhecer os detalhes internos do SQL ou pgvector.

---

## 2. Injeção de Dependências e Configuração
- O `RAGService` deve ser inicializado uma única vez e compartilhado entre as ferramentas MCP.
- Todas as configurações (caminhos de dados, nomes de modelos) devem ser injetadas a partir das variáveis de ambiente lidas no início da execução.

---

## 3. Isolamento de Domínio
- Os dados de diferentes projetos (Rust Star vs FoxOT) devem ser tratados como domínios isolados.
- **Segurança**: Nunca permitir que uma consulta de um projeto acesse metadados de outro, a menos que explicitamente solicitado via ferramenta de administração.

---

## 4. Shared State e Telemetria
- O servidor MCP e o Dashboard utilizam um padrão de **Estado Compartilhado** via arquivo JSON (`data/current_indexing.json`).
- **Unidirecionalidade**: O `RAGService` é o único que escreve no estado. O Dashboard apenas lê. Isso evita condições de corrida e garante a integridade dos dados de monitoramento.
- **Ponte de Logs**: O dashboard deve ler o `mcp_error.log` de forma não-bloqueante para exibir o terminal de eventos em tempo real.
