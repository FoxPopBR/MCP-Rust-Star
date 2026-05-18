# CLAUDE.md — Instruções para Claude (Cowork / Claude Code)

> Idioma: sempre **português brasileiro (pt-BR)**.

---

## ⚠️ Problema Conhecido: Ferramenta Edit Trunca Arquivos

A ferramenta `Edit` do Claude **trunca o arquivo** quando a substituição (`old_string` → `new_string`) é grande. O arquivo fica cortado exatamente após o bloco inserido — o conteúdo original que vinha depois desaparece silenciosamente.

### Como identificar

```bash
# Verificar sintaxe após qualquer edit
python3 -c "
import ast
with open('src/services/rag_service.py', 'rb') as f:
    raw = f.read()
content = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n').decode('utf-8', errors='replace')
try:
    ast.parse(content)
    print('OK')
except SyntaxError as e:
    print(f'ERRO linha {e.lineno}: {e.msg}')
"
```

```bash
# Confirmar conteúdo final do arquivo
python3 -c "
with open('src/services/rag_service.py', 'rb') as f:
    raw = f.read()
lines = raw.replace(b'\r\n', b'\n').decode('utf-8', errors='replace').split('\n')
print(f'Total: {len(lines)} linhas')
for i, l in enumerate(lines[-10:], len(lines)-9):
    print(f'{i}: {repr(l)}')
"
```

### Regra de ouro

> **Nunca usar `Edit` para inserções grandes (> 30 linhas) em arquivos Python.**

---

## Como Editar Arquivos Python com Segurança

### Para inserções pequenas (< 30 linhas)
Use `Edit` normalmente — funciona bem para mudanças cirúrgicas de poucas linhas.

### Para inserções grandes ou adição de métodos/funções

Use um script Python que lê, modifica e reescreve o arquivo:

```python
# Rodar via: python3 << 'EOF' ... EOF
with open('src/services/rag_service.py', 'rb') as f:
    raw = f.read()

content = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n').decode('utf-8')

# Localizar ponto de inserção
marker = '    def list_indexed_sources'
idx = content.find(marker)

novo_metodo = '''
    def meu_novo_metodo(self, param: str) -> dict:
        """Descricao."""
        pass

'''

content = content[:idx] + novo_metodo + content[idx:]

with open('src/services/rag_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"OK — {len(content.splitlines())} linhas")
```

### Para corrigir arquivo truncado

```python
# Identifica onde foi cortado e apenda o conteúdo faltante
with open('src/services/rag_service.py', 'rb') as f:
    raw = f.read()

content = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n').decode('utf-8')
lines = content.split('\n')

# Remover última linha incompleta se necessário
# lines = lines[:-1]

missing = """
    def metodo_faltante(self):
        return self.db.algo()
"""

with open('src/services/rag_service.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + missing)
```

### ❌ Nunca usar heredoc bash para código Python

Heredocs (`cat >> arquivo << 'EOF'`) também truncam conteúdo Python em algumas situações. Prefira sempre scripts Python para manipular arquivos Python.

---

## Verificação Obrigatória Após Qualquer Edição

```bash
cd "C:\Phantasy\MCP Rust Star"

# 1. Checar sintaxe dos 3 arquivos principais
python3 -c "
import ast
for f in ['src/main.py', 'src/services/rag_service.py', 'src/vector_store_postgres.py']:
    with open(f, 'rb') as fh:
        raw = fh.read()
    c = raw.replace(b'\r\n', b'\n').replace(b'\x00', b'').decode('utf-8', errors='replace')
    try:
        ast.parse(c)
        print(f'OK  ({len(c.splitlines())} linhas) — {f}')
    except SyntaxError as e:
        print(f'ERRO linha {e.lineno}: {e.msg} — {f}')
"

# 2. Confirmar mudanças via git diff
git diff --stat src/
```

---

## Estrutura do Projeto

```
src/main.py                      — Entrada MCP, ferramentas (FastMCP)
src/services/rag_service.py      — Orquestração RAG (embed, busca, geração)
src/vector_store_postgres.py     — PostgreSQL + pgvector (prefixo de tabelas: rag_)
src/ollama_client.py             — Cliente Ollama
src/config_manager.py            — Configurações
tools/logger.py                  — Logger (apenas stderr — stdout é JSON-RPC)
```

## Banco de Dados

- Container: `mcp-rust-star-db` (pgvector/pgvector:pg16)
- Banco: `mcp_knowledge` | Usuário: `user` | Senha: `password`
- Tabelas: prefixo `rag_` (ex: `rag_rust_star`, `rag_foxot`, `rag_foxclient`)
- Inspecionar: `docker exec -it mcp-rust-star-db psql -U user -d mcp_knowledge`

## Ferramentas de Busca (novas — adicionadas em 2026-05-18)

| Ferramenta | Quando usar |
|---|---|
| `search_project_knowledge(project_id, question)` | **Principal.** Rápida. Sabe o projeto. |
| `search_all_projects_knowledge(question)` | Lenta. Não sabe o projeto. |
| `cross_project_analysis(searches_json, analysis_prompt)` | Cruzar dados de múltiplos projetos. Fila sequencial. |

## Iniciar o servidor

```bat
run_server.bat
```
