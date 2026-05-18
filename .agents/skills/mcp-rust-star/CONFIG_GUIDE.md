# ⚙️ Guia de Configuração Detalhado: MCP Rust Star

Este guia fornece instruções passo a passo para configurar e calibrar o ambiente industrial do servidor MCP.

## 1. Infraestrutura de Dados (PostgreSQL)

O servidor utiliza o PostgreSQL com a extensão `pgvector` para buscas vetoriais de alta performance.

### 🐳 Setup via Docker (Recomendado)
Certifique-se de que o Docker Desktop está rodando e execute:
```bash
docker-compose up -d
```
O container `mcp-rust-star-db` será criado com:
- **Porta**: 5432
- **Database**: `mcp_knowledge`
- **Extensão**: `vector` (Habilitada automaticamente no boot pelo servidor).

---

## 2. Configuração do Ollama (Modelos)

O servidor é calibrado para os seguintes modelos:
- **Embedding**: `qwen3-embedding:4b`
- **RAG/Visão**: `qwen3.5:4b`

### 🧠 Calibração de Contexto
A janela de contexto está fixada em **12.288 tokens** (12k). 
- **Footprint de VRAM**: ~5.9 GB.
- **Dica**: Se encontrar erros de memória, reduza `num_ctx` no `src/ollama_client.py` para 8192.

---

## 3. Variáveis de Ambiente (.env)

O arquivo `.env` na raiz do projeto deve conter:
```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
EMBEDDING_MODEL=qwen3-embedding:4b
RAG_MODEL=qwen3.5:4b

# Armazenamento
VECTOR_STORE_TYPE=postgres

# PostgreSQL Config
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=mcp_knowledge
POSTGRES_USER=user
POSTGRES_PASSWORD=password
```

---

## 4. Gestão de Preferências (Factory vs User)

O servidor é projetado para funcionar **out-of-the-box** sem configurações manuais.

1. **Padrões de Fábrica (Interno)**: O código já ignora automaticamente arquivos inúteis (`.pyc`, `.dll`, `.exe`, `.log`, `.venv`, etc).
2. **Preferências do Usuário**: Salvas em `data/user_preferences.json` apenas quando você altera algo via comando.
3. **Reset**: A qualquer momento, use `reset_server_settings()` para apagar suas mudanças e voltar ao estado original de fábrica.

### 🔌 Configuração do Cliente MCP (mcp_config_local.json)
Para conectar ao servidor, use apenas as informações de conectividade. **NUNCA** coloque extensões ou filtros aqui:

```json
{
  "mcpServers": {
    "rust-star-knowledge": {
      "command": "C:\\Phantasy\\MCP Rust Star\\.venv\\Scripts\\python.exe",
      "args": ["-m", "src.main"],
      "env": { "PYTHONPATH": "C:\\Phantasy\\MCP Rust Star" }
    }
  }
}
```

### 🔌 Configuração para OpenCode (Modo HTTP Remoto)

Quando o servidor MCP está rodando em modo HTTP, a configuração no `opencode.json` do projeto cliente usa o formato **remote**:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "mcp-rust-star": {
      "type": "remote",
      "url": "http://127.0.0.1:8765/mcp",
      "enabled": true
    }
  }
}
```

**Configuração completa (com GitHub MCP):**

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "github-mcp-server": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-github"],
      "enabled": true
    },
    "mcp-rust-star": {
      "type": "remote",
      "url": "http://127.0.0.1:8765/mcp",
      "enabled": true
    }
  }
}
```

**Como usar:**
1. Inicie o servidor MCP Rust Star em modo HTTP na porta 8765
2. Configure o `opencode.json` do projeto cliente com o bloco acima
3. Reinicie o OpenCode para carregar o servidor remoto

**Notas:**
- O `url` deve apontar para o endpoint `/mcp` do servidor
- O formato é `type: "remote"` + `url` — **não** use `serverURL`
- Se o servidor estiver em outra máquina, troque `127.0.0.1` pelo IP da máquina host

---

## 5. Troubleshooting (Resolução de Problemas)

### O servidor não inicia (EOF Error)
- **Causa**: Alguma biblioteca ou código está dando `print()` no `stdout`.
- **Solução**: Use sempre o decorador `@mcp_tool_with_logging` que desvia o lixo para o `stderr`.

### VRAM não libera
- **Causa**: O Ollama pode segurar o modelo se houver muitas requisições simultâneas.
- **Solução**: Chame a ferramenta `unload_vram()` manualmente via cliente MCP.

### Erro de Conexão Postgres
- **Causa**: Container Docker desligado ou driver `psycopg2` ausente no venv.
- **Solução**: Rode o `run_server.bat`; ele verifica as dependências e o status do sistema.
