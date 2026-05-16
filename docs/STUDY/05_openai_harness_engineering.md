# Estudo de Caso: Harness Engineering na Prática (OpenAI)

## Visão Geral
A OpenAI documentou um experimento radical onde uma equipe pequena (3-7 engenheiros) construiu um produto de software com **1 milhão de linhas de código em 5 meses**, sem que nenhum humano escrevesse código manual.

## O Engenheiro como "Diretor de Sistemas"
Nesta nova realidade, o papel do engenheiro é redefinido:
-   **Decompositor de Objetivos**: O humano define a visão e quebra grandes metas em blocos que os agentes podem processar (janelas de até 6h de autonomia).
-   **Curador de Intenção**: O foco está na arquitetura e no "bom gosto" técnico.
-   **Gargalo de QA**: O esforço humano é movido do "fazer" para o "revisar" e "definir critérios de aceitação".

## Legibilidade do Agente (Agent Legibility)
O ambiente de desenvolvimento é projetado para ser consumido por máquinas, não apenas humanos:
-   **Interfaces Legíveis**: O agente tem acesso ao Chrome DevTools no seu tempo de execução para depurar o frontend.
-   **Logs e Métricas Semânticos**: Logs feitos para que a IA entenda o fluxo de erro rapidamente.
-   **Conhecimento Codificado**: "Se não está no repositório, não existe". Slack, e-mails ou documentos externos são ignorados; tudo deve estar em `ADRs` ou código.

## Governança e Automação Radical
-   **Auto-Merge por Padrão**: Com 15+ PRs por dia, a revisão humana tradicional é impossível. O sistema confia em:
    -   Alta cobertura de testes gerados por agentes.
    -   Monitoramento em tempo real do sistema.
    -   Revisões cruzadas entre agentes (Agente revisando Agente).
-   **Imposição de Invariantes**: Uso de arquitetura de camadas rígida e "linters mecânicos" (também gerados por IA) para garantir que o código não desvie do padrão.

## Coleta de Lixo de Código (Garbage Collection)
A alta velocidade de geração de código cria entropia rapidamente. Para combater isso:
-   Processos automatizados de refatoração ("Janitor Army") rodam continuamente.
-   Eles pagam a dívida técnica diariamente, removendo código morto e centralizando utilitários locais.
-   Isso funciona como um "Coletor de Lixo" para a base de código, mantendo-a limpa e escalável.

## Níveis de Autonomia (L1 a L3)
A OpenAI define que o objetivo é o **Nível 3 (L3)**, onde agentes entregam funcionalidades completas de ponta a ponta, indo muito além de simples sugestões (L1) ou correções pontuais (L2).

---
*Documento gerado para a base de conhecimento STUDY do MCP Rust Star.*
