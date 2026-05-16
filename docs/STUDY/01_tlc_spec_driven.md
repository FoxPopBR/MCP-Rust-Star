# Estudo de Caso: TLC Spec-Driven Development (Tech Leads Club)

## Visão Geral
O **tlc-spec-driven** é um framework de desenvolvimento orientado a especificações projetado para agentes de IA. Ele utiliza um processo adaptativo de 4 fases para garantir que o desenvolvimento seja preciso, rastreável e eficiente, independentemente da complexidade do projeto.

## As 4 Fases Adaptativas
O núcleo do sistema é a capacidade de "auto-dimensionamento" (auto-sizing), onde a profundidade do planejamento é determinada pela complexidade da tarefa:

1.  **SPECIFY (Obrigatório)**: Define o "O QUE". Mapeia requisitos, identifica áreas cinzentas e estabelece a visão.
2.  **DESIGN (Opcional*)**: Focado em arquitetura e componentes. É pulado para mudanças simples e ativado para decisões arquiteturais ou novos padrões.
3.  **TASKS (Opcional*)**: Decomposição em passos atômicos. Pulado se houver ≤ 3 passos óbvios.
4.  **EXECUTE (Obrigatório)**: Implementação real. Mesmo se a fase de Tasks for pulada, a execução começa listando os passos inline.

> [!IMPORTANT]
> **Válvula de Segurança**: Se durante a fase de EXECUTE o agente perceber que a tarefa requer > 5 passos ou tem dependências complexas, ele DEVE parar e criar um `tasks.md` formal.

## Estrutura do Projeto (.specs/)
O framework organiza o conhecimento em diretórios estruturados para facilitar o consumo pelo agente:
-   **project/**: Visão, metas, roadmap e memória de decisões (`STATE.md`).
-   **codebase/**: Análise de projetos existentes (Brownfield), cobrindo stack, arquitetura, convenções e preocupações (`CONCERNS.md`).
-   **features/**: Especificações de funcionalidades individuais (`spec.md`, `design.md`, `tasks.md`).
-   **quick/**: Tarefas ad-hoc rápidas.

## Estratégia de Gerenciamento de Contexto
Para evitar o transbordamento da janela de contexto e manter o raciocínio afiado, o sistema aplica limites rigorosos:
-   **Carga Base (~15k tokens)**: Projeto, Roadmap e Memória de Decisões.
-   **Carga Sob Demanda**: Documentos de arquitetura ou especificações de funcionalidades específicas.
-   **Meta de Contexto**: Manter o total < 40k tokens, reservando 160k+ para raciocínio e saída.

## Cadeia de Verificação de Conhecimento
Antes de tomar qualquer decisão técnica, o agente deve seguir esta ordem estritamente:
1.  **Codebase**: Verificar código e padrões existentes.
2.  **Documentação do Projeto**: README, `/docs`, `.specs/`.
3.  **MCP (Base de Conhecimento)**: Consultar bases RAG locais.
4.  **Web Search**: Documentação oficial e fontes reputadas.
5.  **Sinalizar Incerteza**: Se os passos 1-4 falharem, o agente deve dizer "Não sei" em vez de fabricar informações.

## Delegação para Sub-Agentes
O framework incentiva o uso de sub-agentes para tarefas pesadas, mantendo o agente orquestrador leve. O orquestrador planeja e o sub-agente executa, recebendo apenas o contexto necessário para aquela tarefa específica (princípio do menor privilégio de contexto).

## Integração de Skills
-   **Diagramas**: Uso preferencial do `mermaid-studio` para visualização.
-   **Exploração de Código**: Uso do `codenavi` para mapeamento e análise de dependências.

---
*Documento gerado para a base de conhecimento STUDY do MCP Rust Star.*
