# ADR 0006: Arquitetura de Monitoramento via Shared State (Dashboard)

- **Status**: Aceito
- **Data**: 15/05/2026
- **Autor**: Antigravity

## Contexto
O servidor MCP roda como um processo de background na IDE, tornando-o uma "caixa preta" para o usuário. Precisávamos de uma forma de monitorar o progresso da indexação (Novos, Cache, Erros) e visualizar logs em tempo real sem interferir no canal `stdout` do protocolo JSON-RPC.

## Decisão
Implementar um **Dashboard Independente** baseado em `rich` que se comunica com o servidor via **Estado Compartilhado (Shared State)**.
- O servidor escreve o estado atual (projeto, arquivo, stats) em `data/current_indexing.json` de forma atômica.
- O Dashboard lê este arquivo e o `mcp_error.log` em um loop de 4Hz.
- Uso de **Caminhos Absolutos** calculados no boot para garantir que ambos os processos encontrem os arquivos independentemente do diretório de execução.

## Consequências
- **Positivas**: 
    - Transparência total da operação em background.
    - Desacoplamento total: o Dashboard pode ser fechado ou aberto sem afetar o servidor.
    - Zero interferência no protocolo JSON-RPC (MCP).
- **Negativas**: 
    - Pequeno overhead de I/O em disco para atualizações de estado (minimizado pela frequência de 4Hz).
