# Estudo de Caso: Harness Design para Apps de Longa Duração (Anthropic)

## Visão Geral
A Anthropic explorou como levar o modelo Claude além do básico em tarefas complexas, focando em duas áreas: **Design de Frontend de Alta Qualidade** e **Engenharia de Software Autônoma de Longa Duração**.

## A Estrutura Multi-Agente (Inspirada em GANs)
Para quebrar o teto de desempenho, a Anthropic adotou uma arquitetura de três agentes:

1.  **PLANNER (Planejador)**: Transforma um prompt simples (1-4 frases) em uma especificação de produto ambiciosa. Foca no contexto do negócio e design técnico de alto nível, evitando detalhes granulares que possam causar erros em cascata.
2.  **GENERATOR (Gerador)**: Implementa as funcionalidades em sprints. Trabalha em um ciclo de "Sprint Contract" (contrato de sprint), onde ele propõe o que vai fazer antes de escrever o código.
3.  **EVALUATOR (Avaliador)**: O "crítico". Usa ferramentas como **Playwright** para interagir com a aplicação real (clicar em botões, verificar estados de DB).

## Resolvendo a "Ansiedade de Contexto"
Modelos tendem a perder coerência quando o contexto enche, ou pior, começam a "encerrar o trabalho precocemente" por medo de atingir o limite (Ansiedade de Contexto).
-   **Context Resets**: Em vez de apenas resumir (compactar), o sistema limpa o contexto e inicia uma nova sessão com um **Handoff Artifact** estruturado contendo o estado atual e próximos passos. Isso garante uma "folha limpa" para o agente.

## Transformando o Subjetivo em Graduável (Frontend Design)
Para melhorar o design, o Avaliador utiliza 4 critérios objetivos para julgar o subjetivo:
-   **Design Quality**: O design parece um todo coerente? (Cores, Tipografia, Mood).
-   **Originalidade**: Existem decisões customizadas ou é apenas um template padrão de IA? (Penaliza "AI slop").
-   **Craft (Habilidade)**: Execução técnica (espaçamento, contraste, hierarquia).
-   **Funcionalidade**: Usabilidade independente da estética.

## O Loop de Auto-Correção e Negociação
Antes de cada sprint, o Gerador e o Avaliador negociam o que "Pronto" (Done) significa. O Avaliador atua como um QA rigoroso, navegando na página ao vivo, tirando screenshots e falhando a sprint se houver qualquer divergência do contrato. Este processo pode levar até 4-5 horas de execução autônoma.

## Lições de Evolução dos Modelos
Com o lançamento de modelos mais capazes (ex: Claude 3.5/4.5+), algumas partes do harness tornam-se redundantes. A Anthropic notou que modelos mais novos gerenciam melhor o contexto longo, permitindo simplificar o harness removendo a estrutura de sprints e focando apenas no loop Planejador-Avaliador para tarefas que estão no limite da capacidade do modelo.

---
*Documento gerado para a base de conhecimento STUDY do MCP Rust Star.*
