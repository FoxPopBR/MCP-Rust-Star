# Estudo de Caso: Harness Engineering (Martin Fowler / Birgitta Böckeler)

## Visão Geral
O conceito de **Harness Engineering** define que a eficácia de um agente de codificação não depende apenas do modelo de linguagem (LLM), mas do "arreio" (harness) construído ao redor dele.
**Equação Fundamental: Agente = Modelo + Harness.**

## Controles de Feedforward e Feedback
Para confiar em agentes autônomos, o harness deve implementar dois tipos de controles:

### 1. Guias (Feedforward)
Antecipam o comportamento indesejado e tentam preveni-lo ANTES do agente agir.
-   Exemplos: Regras de codificação, documentos de arquitetura (ADRs), templates de serviço.
-   Objetivo: Aumentar a probabilidade de o agente acertar na primeira tentativa.

### 2. Sensores (Feedback)
Observam a ação do agente e ajudam na auto-correção.
-   Exemplos: Testes unitários, linters, revisões de código automatizadas.
-   Objetivo: Detectar falhas e fornecer sinais claros para que o agente corrija o erro sem intervenção humana.

## Categorias de Execução: Computacional vs. Inferencial

-   **Computacional (Determinístico)**: Executado pela CPU. Rápido e barato.
    -   *Exemplos*: Compiladores, Type Checkers, Linters, Testes de Cobertura.
    -   *Vantagem*: Resultados confiáveis e binários.
-   **Inferencial (Probabilístico)**: Executado pela GPU/NPU. Lento e caro.
    -   *Exemplos*: "LLM as Judge", Análise Semântica, Revisão de Arquitetura por IA.
    -   *Vantagem*: Consegue julgar "gosto", "elegância" e conformidade com princípios subjetivos.

## As Três Categorias de Harness

1.  **Maintainability Harness (Manutenibilidade)**: Regula a qualidade interna do código (duplicação, complexidade ciclomática). É o mais fácil de construir com ferramentas existentes.
2.  **Architecture Fitness Harness (Conformidade Arquitetural)**: Garante que a aplicação segue características de design (performance, padrões de logging, limites de módulos). Utiliza "Fitness Functions".
3.  **Behaviour Harness (Comportamento)**: O "elefante na sala". Garante que o software faz o que deveria fazer funcionalmente. É o mais difícil, pois testes gerados por IA muitas vezes confirmam o erro do próprio agente.

## A Lei de Ashby e a Redução de Variedade
Aplicada à IA, a **Lei da Variedade Requisita** sugere que, como um LLM pode produzir quase qualquer coisa (variedade infinita), o harness deve reduzir essa variedade definindo **Topologias** claras. Ao limitar o espaço de soluções possíveis (ex: "neste projeto usamos apenas Hexagonal Architecture com FastAPI"), o harness torna-se muito mais eficaz na governança.

## O Papel do Humano: O "Steering Loop"
O trabalho do engenheiro humano muda de "escrever código" para "iterar no harness". Se um agente comete o mesmo erro duas vezes, o humano não deve apenas corrigir o código, mas **melhorar os guias ou sensores** para que o erro não se repita.

---
*Documento gerado para a base de conhecimento STUDY do MCP Rust Star.*
