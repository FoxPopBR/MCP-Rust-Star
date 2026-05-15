# Rust Star MCP Knowledge Server

Este é um servidor MCP projetado para fornecer inteligência e base de conhecimento para o projeto **Rust Star**. Ele utiliza **Ollama** local para embeddings e geração de texto, e **ChromaDB** para armazenamento vetorial.

## Requisitos

- Python 3.10+
- [Ollama](https://ollama.com/) rodando localmente.
- Modelos baixados no Ollama:
  - `ollama pull qwen3-embedding:4b`
  - `ollama pull qwen3.5:9b`

## Instalação

1. Clone ou copie os arquivos para a pasta do servidor.
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Verifique o arquivo `.env` para garantir que as URLs e nomes de modelos estão corretos.

## Uso do Servidor MCP

Para rodar o servidor:
```bash
python -m src.main
```

### Ferramentas Disponíveis

1. **`index_content(content, source)`**: Envia textos para serem memorizados pelo servidor. Ex: Lore do jogo, regras de arquitetura Rust, etc.
2. **`ask_rust_star(question)`**: Faz uma pergunta que utiliza a base de conhecimento indexada para responder com precisão.
3. **`check_ollama_status()`**: Verifica se a conexão com o Ollama está ativa e os modelos carregados.
4. **`clear_knowledge_base()`**: Apaga toda a memória do servidor.

## Estrutura do Projeto

- `src/main.py`: Ponto de entrada e definição de ferramentas MCP.
- `src/ollama_client.py`: Comunicação com a API do Ollama.
- `src/vector_store.py`: Abstração do banco vetorial ChromaDB.
- `src/services/rag_service.py`: Lógica principal do pipeline RAG.
- `data/`: Diretório de persistência do banco de dados vetorial.
