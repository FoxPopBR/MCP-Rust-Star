# Referência de Links e Fontes de Estudo (LLM & Agentic Engineering)

Abaixo estão os links fundamentais que serviram de base para esta documentação, com suas respectivas descrições e relevância para o projeto MCP Rust Star.

| Link | Descrição | Importância Técnica |
| :--- | :--- | :--- |
| [TLC Spec-Driven Development](https://agent-skills.techleads.club/skills/tlc-spec-driven/) | Framework de planejamento e execução adaptativa do Tech Leads Club. | Define as fases de Specify/Design/Tasks/Execute e gestão de contexto. |
| [GSD-2 (GitHub)](https://github.com/gsd-build/gsd-2) | Sistema autônomo de meta-prompting e engenharia de contexto. | Referência para automação de longa duração, persistência em DB e auto-commit. |
| [Harness Engineering (Martin Fowler)](https://martinfowler.com/articles/harness-engineering.html) | Mentalidade de construção de "arreios" (harnesses) para agentes de codificação. | Introduz o conceito de Feedforward (Guias) e Feedback (Sensores). |
| [Anthropic: Harness Design for Long-Running Apps](https://www.anthropic.com/engineering/harness-design-long-running-apps) | Estudo sobre o uso de Claude para engenharia autônoma e design de frontend. | Explora arquiteturas Multi-Agente (Planner/Generator/Evaluator) e Context Resets. |
| [OpenAI: Harness Engineering Case Study](https://openai.com/pt-BR/index/harness-engineering/) | Relato da OpenAI sobre a construção de 1M LOC em 5 meses sem código manual. | Introduz o conceito de "Agent Legibility", "Garbage Collection" e o papel do "System Director". |
| [CONTEXT.md Format (Matt Pocock)](https://github.com/mattpocock/skills/blob/main/skills/engineering/grill-with-docs/CONTEXT-FORMAT.md) | Padronização para documentação de Linguagem Ubíqua em projetos de IA. | Crucial para garantir que o agente não alucine termos e entenda as relações do domínio. |

## Como utilizar estes recursos
Estes documentos em `docs/STUDY/` devem ser consultados sempre que o projeto enfrentar:
1.  **Complexidade Crescente**: Usar as fases do *TLC Spec-Driven*.
2.  **Divergência Semântica**: Implementar ou atualizar o *CONTEXT.md*.
3.  **Necessidade de Autonomia**: Revisar as práticas de *Harness Engineering* da OpenAI/Anthropic.
4.  **Falhas Repetitivas**: Aplicar a lógica de *Feedforward/Feedback* do Martin Fowler.

---
*Documento gerado para a base de conhecimento STUDY do MCP Rust Star.*
