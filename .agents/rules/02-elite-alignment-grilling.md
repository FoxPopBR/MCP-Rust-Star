# Regra 02: Protocolo de Alinhamento "Grilling" (Sabatina)

Antes de escrever qualquer código ou aplicar mudanças arquiteturais, o agente DEVE passar pela fase de alinhamento para evitar "vibe coding".

## 1. O Ritual da Sabatina
O agente deve questionar o usuário (ou a si mesmo em modo plano) sobre:
- **Premissas Ocultas**: O que estamos assumindo que pode não ser verdade? (Ex: "O Ollama está sempre rodando na porta padrão?").
- **Estados de Erro**: Como o sistema deve se comportar quando o Postgres falhar ou o modelo `qwen3` retornar lixo?
- **Limites de Escopo**: Esta mudança afeta apenas o projeto *Rust Star* ou impacta *FoxOT* e *FoxClient*?
- **Restrições de Recurso**: O impacto na VRAM foi considerado ao sugerir um novo modelo ou aumento de contexto?

## 2. Critérios de Aceite Claros
Nenhuma tarefa é considerada "pronta para execução" sem uma lista de critérios de aceite que possam ser validados via logs ou testes.

## 3. Alinhamento com o CONTEXT.md
Sempre verifique se os termos usados na nova implementação estão definidos no `CONTEXT.md`. Se não estiverem, sugira a atualização do dicionário do projeto.
