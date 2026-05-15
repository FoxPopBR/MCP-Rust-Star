# Regra 06: Arquitetura Limpa e Separação de Responsabilidades

Para garantir que o MCP Rust Star seja escalável e fácil de manter, seguimos uma arquitetura desacoplada.

## 1. Camadas do Sistema

### Camada de Interface (MCP Server) - `src/main.py`
- **Responsabilidade**: Definir ferramentas MCP e lidar com a comunicação via STDIO.
- **Regra**: Esta camada não deve conter lógica de negócio pesada ou manipulação direta do banco de dados vetorial. Ela deve apenas chamar os serviços apropriados.

### Camada de Serviço (RAG Service) - `src/services/rag_service.py`
- **Responsabilidade**: Orquestrar o pipeline de RAG (embeddings, busca, geração).
- **Regra**: Deve ser independente da interface. Se decidirmos trocar o MCP por uma API REST no futuro, esta camada deve permanecer intocada.

### Camada de Persistência (Vector Store) - `src/vector_store.py`
- **Responsabilidade**: Abstrair o ChromaDB e operações de persistência de projetos.
- **Regra**: Nenhuma outra camada deve conhecer os detalhes internos do ChromaDB.

---

## 2. Injeção de Dependências e Configuração
- O `RAGService` deve ser inicializado uma única vez e compartilhado entre as ferramentas MCP.
- Todas as configurações (caminhos de dados, nomes de modelos) devem ser injetadas a partir das variáveis de ambiente lidas no início da execução.

---

## 3. Isolamento de Domínio
- Os dados de diferentes projetos (Rust Star vs FoxOT) devem ser tratados como domínios isolados.
- **Segurança**: Nunca permitir que uma consulta de um projeto acesse metadados de outro, a menos que explicitamente solicitado via ferramenta de administração.
