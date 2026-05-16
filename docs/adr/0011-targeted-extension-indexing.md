# ADR-0011: Indexação Cirúrgica por Extensão sem Whitelist

## Status
Implementado (15/05/2026)

## Contexto

A ferramenta `index_directory` existente passa por `_walk_and_index_sync`, que chama `rag.config.is_ignored()` em cada arquivo. Essa função verifica a whitelist global (`allowed_extensions`) antes de qualquer outra coisa — se a extensão não estiver na lista, o arquivo é silenciosamente ignorado, mesmo que o usuário o queira explicitamente.

Isso criava uma barreira inconveniente: para indexar arquivos de uma extensão específica não coberta pela whitelist padrão, o usuário era obrigado a modificar a whitelist global via `update_indexing_settings` — uma operação com efeito colateral em todos os projetos.

O requisito identificado: uma ferramenta que indexe **exatamente o que for pedido**, sem filtros globais, com suporte a múltiplas extensões em uma única chamada.

## Decisão

Implementar dois novos MCP tools que chamam `rag.index_file_by_path()` diretamente, contornando a camada de whitelist:

### `index_folder_by_extension`
- Parâmetros: `project_id`, `folder_path`, `extensions` (vírgula), `background`
- Caminha a pasta recursivamente via `_index_folder_ext_sync` (helper sync)
- Filtra por extensões *manualmente* no walk, sem chamar `is_ignored()`
- `extensions="*"` aceita qualquer arquivo
- Roda em background via `asyncio.create_task`; atualiza `_embed_state` para visibilidade no dashboard

### `index_files`
- Parâmetros: `project_id`, `files` (caminhos absolutos separados por vírgula)
- Indexa arquivos específicos diretamente, sem nenhum filtro
- Síncrona (foreground): retorna relatório consolidado imediatamente
- Adequada para arquivos isolados onde o feedback imediato é mais útil

### Invariante preservada
`rag.index_file_by_path()` não verifica whitelist — ela lê e indexa incondicionalmente. A whitelist existe apenas na camada de descoberta (`_walk_and_index_sync` / `is_ignored()`). As novas tools exploram esse fato de forma intencional.

## Consequências

- **Positivas**:
  - Flexibilidade total para adicionar qualquer extensão a um projeto específico sem alterar configuração global
  - Suporte a múltiplas extensões em uma única chamada (ex: `".rs,.toml,.md"`)
  - Integração com dashboard via `_embed_state` (pré-scan + progresso por arquivo)
  - Cache MD5 garante que re-execuções são seguras e idempotentes

- **Negativas / Riscos**:
  - Sem filtro de whitelist, arquivos binários ou muito grandes podem ser enviados ao Ollama. O usuário é responsável por especificar extensões sensatas.
  - `index_folder_by_extension` não tem retry automático (ao contrário de `_walk_and_index_sync`). Falhas individuais são logadas mas não retentadas.

- **Não alterado**:
  - `index_directory` continua funcionando com whitelist, para o fluxo padrão de indexação em massa de projetos completos.
