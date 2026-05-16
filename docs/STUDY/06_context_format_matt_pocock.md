# Padronização: CONTEXT.md (Matt Pocock / Engineering Skills)

## Visão Geral
O arquivo `CONTEXT.md` é a ferramenta definitiva para alinhar a linguagem e o entendimento entre o humano, o especialista do domínio e o agente de IA. Ele define a "Linguagem Ubíqua" do projeto.

## Estrutura do Documento
Um `CONTEXT.md` eficaz deve conter:

1.  **Descrição do Contexto**: O que é este projeto e por que ele existe.
2.  **Language (Linguagem)**: Definições estritas de termos.
    -   *Exemplo*: **Pedido**: Um compromisso de compra. *Evitar*: Transação, compra.
3.  **Relationships (Relacionamentos)**: Como as entidades se conectam (cardinalidade).
    -   *Exemplo*: Um **Pedido** produz um ou mais **Faturas**.
4.  **Example Dialogue (Diálogo de Exemplo)**: Uma conversa entre um desenvolvedor e um especialista para mostrar os termos em uso natural.
5.  **Flagged Ambiguities (Ambiguidades Sinalizadas)**: Registra conflitos resolvidos (ex: "descobrimos que 'conta' estava sendo usado para 'Usuário' e 'Cliente' ao mesmo tempo; agora são distintos").

## Regras de Ouro
-   **Seja Opinativo**: Escolha um termo e proíba os outros.
-   **Definições Curtas**: Máximo de uma frase. Defina o que o termo É, não o que ele FAZ.
-   **Específico do Domínio**: Não inclua conceitos gerais de programação (timeouts, erros). Apenas o que é único para este negócio.
-   **Buscabilidade**: Use nomes de termos em **negrito** para facilitar a varredura visual e por IA.

## Multi-Contextos (CONTEXT-MAP.md)
Para repositórios grandes, um único arquivo não basta. Usa-se um `CONTEXT-MAP.md` na raiz que lista os sub-contextos (Ordering, Billing, Fulfillment) e como eles se relacionam via eventos ou tipos compartilhados.

## Por que isso é vital para LLMs?
LLMs são "alucinadores de nomes". Se você não define que o termo correto é `Fulfillment`, o modelo pode começar a usar `Shipping`, `Delivery` ou `Dispatch` de forma aleatória, quebrando a consistência do código e da documentação. O `CONTEXT.md` serve como a **âncora semântica** do agente.

---
*Documento gerado para a base de conhecimento STUDY do MCP Rust Star.*
