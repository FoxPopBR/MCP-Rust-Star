# ADR-0008: Super Whitelist e Deep Scan Strategy

## Status
Proposto / Em Implementação

## Contexto
Durante a indexação em massa dos projetos FoxOT e Rust Star, identificou-se que a configuração padrão ("Strict Whitelist") e o respeito ao `.gitignore` estavam impedindo a captura de arquivos críticos de lógica de negócio (como `.bat`, `.cfg`, `.csv`, `.otmod` e arquivos dentro de pastas `libs` ou `assets`). Estimativas iniciais mostravam ~3.000 arquivos, enquanto o scan real revelou mais de 15.000 arquivos elegíveis.

## Decisão
Decidimos adotar uma abordagem de **"Deep Scan" (Varredura Profunda)** com os seguintes pilares:

1.  **Super Whitelist**: Expandir a lista de extensões permitidas para incluir todas as linguagens do ecossistema (Rust, C++, Lua, Python), scripts de automação (`.bat`, `.ps1`, `.sh`, `.cmake`) e formatos de dados técnicos (`.csv`, `.cfg`, `.conf`, `.properties`).
2.  **Desativação de Filtros Restritivos**: Desativar o uso do `.gitignore` para a indexação de conhecimento (conhecimento != código fonte git) e remover pastas como `assets`, `libs` e `vendor` da lista negra global.
3.  **Persistência Dupla**: As extensões foram adicionadas ao `defaults.json` (padrão de fábrica) e as regras de scan profundo ao `user_preferences.json`.

## Consequências
- **Positivas**: Cobertura de 100% do conhecimento técnico do projeto; capacidade da IA de entender scripts de inicialização e configurações complexas.
- **Negativas**: Aumento no tempo de indexação inicial (de minutos para horas); maior consumo de espaço no banco de dados vetorial.
- **Risco**: Possível ruído caso arquivos de dados massivos (ex: logs gigantes) não estejam na pasta de `logs/` (que continua bloqueada).
