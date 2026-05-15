# ADR 0004: Sincronização de Janela de Contexto (Ollama vs. Chunking)

## Status
Aceito

## Contexto
Durante o embed do projeto `FoxClient`, identificamos dois problemas críticos:
1.  **Erro de Contexto**: O erro `input length exceeds context length` ocorria porque o Ollama estava configurado com 8k de contexto, enquanto tentávamos enviar fragmentos (chunks) que se aproximavam desse limite.
2.  **Desconexão do Servidor**: Ocorreu um erro `Server disconnected` durante o processamento do arquivo `catalog-content.json` (1MB), coincidindo com a alteração manual das configurações no aplicativo Ollama.

## Decisões
1.  **Padronização para 16k**: O usuário elevou o limite de contexto no Ollama para 16.384 tokens.
2.  **Ajuste de Granularidade**: Reduzimos o `chunk_size` para **8.000 caracteres**. Esta configuração é conservadora e garante estabilidade absoluta mesmo em arquivos densos, pois 8k caracteres resultam em aproximadamente 2k-3k tokens, deixando margem abundante para a janela de 16k do Ollama.
3.  **Tolerância a Falhas**: Validamos que o worker de background continua processando a fila mesmo após falhas em arquivos individuais, registrando-os para posterior re-tentativa (`retry_failed_files`).

## Consequências
- **Estabilidade**: O pipeline tornou-se resiliente a variações de densidade de tokens.
- **Confiabilidade**: Arquivos que falham por motivos externos (como reinicialização do Ollama) são isolados e não interrompem a indexação do restante do projeto.
- **Rastreabilidade**: O erro no arquivo `catalog-content.json` está documentado no log e será corrigido via retry ao final da sessão.
