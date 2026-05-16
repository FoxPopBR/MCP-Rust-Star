# Lógica e Prática de LLM: O Novo Paradigma da Engenharia de Software

Este documento consolida os princípios modernos de desenvolvimento de software utilizando Agentes de IA, baseando-se nas práticas de elite da OpenAI, Anthropic, Martin Fowler e Tech Leads Club.

## 1. O Axioma Fundamental: Agente = Modelo + Harness
O modelo (GPT-4, Claude 3.5, etc.) é apenas o motor. O sucesso de um projeto depende do **Harness** (Arreio/Suporte) — a infraestrutura de ferramentas, regras, processos de validação e gerenciamento de contexto que envolvem o modelo.

## 2. Engenharia de Contexto (O Combustível)
O contexto não é apenas o histórico da conversa; é a memória ativa do sistema.
-   **Poda e Compactação**: Manter o contexto leve (< 40k tokens) para maximizar o raciocínio.
-   **Reset vs. Resumo**: Em tarefas longas, prefira o **Context Reset** (limpar tudo e começar do zero com um artefato de handoff) para evitar a "ansiedade de contexto" e alucinações.
-   **Memória Persistente**: Use bancos de dados (`STATE.md`, `gsd.db`) em vez de confiar na memória de curto prazo da sessão.

## 3. Harness Engineering: Feedforward e Feedback
O desenvolvimento deve ser governado por circuitos de controle:
-   **Feedforward (Prevenção)**: Use `CONTEXT.md`, `ADR.md` e regras de arquitetura para guiar o agente ANTES de ele escrever o código. Reduza a variedade de soluções possíveis para que o agente não se perca.
-   **Feedback (Correção)**: Implemente sensores **Computacionais** (Testes, Linters) e **Inferenciais** (IA revisando IA). Use ferramentas como Playwright para que a IA "veja" e "sinta" o código funcionando em tempo real.

## 4. O Ciclo de Vida do Desenvolvimento Agentic
O processo moderno abandona o "coding" manual em favor de um fluxo de direção:
1.  **Specify**: Humano define a intenção clara.
2.  **Plan/Design**: Agente expande a intenção em especificações técnicas e contratos.
3.  **Negotiate**: Agente Gerador e Agente Avaliador concordam sobre os critérios de sucesso.
4.  **Execute**: Implementação autônoma com commits atômicos e rastreabilidade.
5.  **Validate**: Verificação rigorosa por um agente independente (Evaluator) usando ferramentas de runtime.
6.  **Garbage Collection**: Refatoração contínua para manter a saúde da base de código.

## 5. Legibilidade do Agente (Agent Legibility)
Construa software para ser lido por IAs:
-   **Everything in Repo**: O código deve ser a única fonte de verdade.
-   **Semantic Tooling**: Dê ferramentas poderosas ao agente (LSPs, acesso ao Browser, Shell Interativo, MCP Servers).
-   **Custom Diagnostics**: Crie logs e erros que incluam instruções de como a IA deve corrigi-los (ex: "Erro X: tente rodar o comando Y para resolver").

## 6. O Humano como Diretor de Orquestra
O papel do engenheiro evolui:
-   **Menos Teclado, Mais Cérebro**: Você não escreve linhas; você escreve regras e validações.
-   **Iteração no Harness**: Se o agente falha, não corrija apenas o erro. **Corrija o Harness** (adicione uma regra, melhore o teste, ajuste o contexto).
-   **Gosto Técnico**: Sua principal contribuição é o "technical taste" — saber o que é uma arquitetura elegante e o que é "AI slop" (código genérico e volumoso).

## Conclusão
A engenharia de software com LLMs não é sobre "pedir para a IA fazer"; é sobre **projetar sistemas que permitem que a IA faça com segurança, escala e qualidade superior à humana**.

---
*Documento gerado para a base de conhecimento STUDY do MCP Rust Star.*
