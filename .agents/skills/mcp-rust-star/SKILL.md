name: mcp-rust-star
description: Manual Industrial Definitivo do ecossistema MCP Rust Star. Use para operar RAG multimodal, PostgreSQL, gestão de VRAM e filtros avançados com rigor técnico de 2026.

# 📔 Grimório de Operação: MCP Rust Star Knowledge Server (v1.1)

Este documento é a autoridade mestre para operação do servidor de conhecimento industrial. Ele detalha cada ferramenta, configuração e protocolo de elite para os projetos Rust Star, FoxOT e FoxClient.

---

## 🏗️ 1. Infraestrutura e Inicialização

O servidor utiliza uma arquitetura de **Alta Fidelidade**. Para detalhes técnicos sobre o setup do Docker, PostgreSQL e variáveis de ambiente, consulte o [Guia de Configuração (CONFIG_GUIDE.md)](CONFIG_GUIDE.md).

- **Banco de Dados**: PostgreSQL com extensão `pgvector`.
- **Inteligência**: Ollama local (qwen3-embedding:4b e qwen3.5:4b).
- **Monitoramento**: Dashboard em tempo real via `dashboard.bat` (UI Rich no Terminal).
- **Memória**: Janela calibrada de **12.288 tokens** (Equilíbrio VRAM/Precisão).

### 🔄 Protocolo de Boot (Auto-Cura)
Execute sempre via `run_server.bat`. O script realiza:
1. `Saneamento de PID`: Mata instâncias órfãs de `src.main`.
2. `Check de Dependência`: Valida se o Ollama está na porta 11434.
3. `VirtualEnv Health`: Verifica e instala bibliotecas faltantes automaticamente.

---

## 🛠️ 2. Catálogo Exaustivo de Ferramentas (Tools)

### 📁 Gestão de Projetos
| Ferramenta | Parâmetros | Descrição |
| :--- | :--- | :--- |
| `register_project` | `project_id` (str), `path` (str) | Vincula um nome a um diretório físico. Essencial para o isolamento de dados. |
| `list_projects` | - | Retorna todos os workspaces registrados e seus caminhos. |

### 🧠 Indexação e Visão (Embeddings)
| Ferramenta | Parâmetros | Descrição |
| :--- | :--- | :--- |
| `index_file` | `path` (str) | Indexa um arquivo individual (.py, .md, .pdf). Detecta o projeto pelo path. |
| `index_directory`| `path` (str), `extension` (str), `use_gitignore` (bool) | **Motor Batch**. Indexa pastas inteiras. Usa **Sessão de VRAM** para performance. |
| `index_image` | `path` (str) | **Multimodal**. Usa o qwen3.5 para "ver" screenshots/diagramas e indexar o texto. |

### 🔍 Recuperação e Resposta (RAG)
| Ferramenta | Parâmetros | Descrição |
| :--- | :--- | :--- |
| `ask_knowledge_base` | `question` (str), `project_id` (str) | Consulta principal. Recupera até 5 fragmentos (Top-K) para síntese profunda. |
| `ask_rust_star` | `question` (str) | Atalho de alta prioridade para o projeto principal. |

### ⚙️ Gestão de Sistema e Hardware
| Ferramenta | Parâmetros | Descrição |
| :--- | :--- | :--- |
| `get_server_settings` | - | Mostra o JSON de filtros ativos, Auto-Vision e tamanhos de chunk. |
| `update_server_settings`| `ignored_extensions` (list), `auto_index_images` (bool), `chunk_size` (int) | Altera o comportamento do servidor em tempo real. |
| `get_gpu_status` | - | Relatório em tempo real do uso de VRAM (nvidia-smi). |
| `unload_vram` | - | Comando de "Ejeção de Emergência" para limpar a GPU. |
| `clear_knowledge_base`| `project_id` (str, opcional) | Reset cirúrgico ou total da base de dados. |

---

## ⚙️ 3. Manual de Configuração (`mcp_settings.json`)

Você pode ajustar estes valores via `update_server_settings`:

1. **`ignored_extensions`**: Lista de arquivos que o servidor ignora no `index_directory`.
   - *Padrão*: `[".log", ".exe", ".dll", ".pyc", ".venv", ".git"]`.
2. **`auto_index_images`**: Se `True`, a ferramenta `index_directory` indexará imagens sem pedir permissão.
3. **`chunk_size`**: Tamanho de cada pedaço de informação (Padrão: 12.000 chars).
4. **`chunk_overlap`**: Sobreposição para manter continuidade semântica (Padrão: 1.000 chars).
5. **`use_gitignore`**: Quando ativo, o servidor respeita as regras do seu arquivo `.gitignore` local.

---

## 💡 4. Exemplos Práticos de Elite

### Caso A: Indexação Inteligente de Novo Projeto
> "Registre o projeto FoxClient em C:\Projetos\FoxClient. Depois, indexe a pasta completa ignorando arquivos .tmp e usando o gitignore."
- **Ação**: `register_project` -> `index_directory(path=..., use_gitignore=True)`

### Caso B: Diagnóstico Multimodal de Erro
> "Tirei um print do erro de compilação. Indexe esta imagem: C:\prints\error_01.png."
- **Ação**: `index_image(path="C:\prints\error_01.png")`. O servidor registrará: *"ORIGEM VISUAL: error_01.png | LOCALIZAÇÃO: C:\prints\..."*

### Caso C: Consulta RAG Global
> "Qual a lógica de conexão com o banco de dados em todos os meus projetos?"
- **Ação**: `ask_knowledge_base(question="...", project_id=None)`. O sistema buscará no PostgreSQL cruzando dados de todos os workspaces.

---

## 🛡️ 5. Protocolos de Segurança e Performance

- **Zero-Waste VRAM**: O sistema garante que após cada tarefa, a memória de vídeo seja devolvida ao Windows via `unload_vram`.
- **Estabilidade por Subdivisão**: Arquivos que saturam a VRAM são automaticamente divididos em fragmentos menores e re-indexados recursivamente.
- **Isolamento de Contexto**: Nunca responda uma pergunta de um projeto usando dados de outro sem permissão.
- **Integridade de Log**: Se algo falhar, consulte `logs/mcp_error.log` ou acompanhe o **Terminal de Eventos** no Dashboard.

---
*Este manual é um artefato de Engenharia de Elite. Siga-o para garantir a soberania do conhecimento no ecossistema Rust Star.*
