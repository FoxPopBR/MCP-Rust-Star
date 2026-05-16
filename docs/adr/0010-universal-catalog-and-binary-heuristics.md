# ADR-0010: Universal Knowledge Catalog and Binary Heuristics

## Status
Proposto

## Contexto
O servidor MCP Rust Star evoluiu de uma ferramenta específica para um projeto para um motor RAG de propósito geral. A whitelist anterior era restritiva demais para usuários que trabalham com múltiplas stacks (Android, Web, Backend, Cloud). Além disso, o processo de descoberta de novas extensões (`scan_extensions`) era passivo, não diferenciando arquivos de texto de binários "lixo".

## Decisão
1.  **Universal Whitelist**: Expandir o `defaults.json` para incluir o "Top 50" de linguagens e formatos industriais, garantindo que o servidor funcione "out-of-the-box" para quase qualquer repositório.
2.  **Binary Heuristics**: Implementar no `scan_extensions` uma verificação sensorial: ao encontrar uma extensão desconhecida, o sistema lerá o cabeçalho do arquivo para detectar caracteres nulos (`\x00`). 
3.  **Rotulagem de Descoberta**: Marcar extensões candidatas como `[TEXTO]` ou `[BINÁRIO]` no relatório de scan.

## Consequências
- **Positivas**: Redução drástica da fricção de configuração inicial; proteção contra indexação acidental de binários gigantes que não estavam na blacklist explícita.
- **Negativas**: Pequeno overhead de I/O durante o `scan_extensions` (apenas para o primeiro arquivo encontrado de cada extensão desconhecida).
