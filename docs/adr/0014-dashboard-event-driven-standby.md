# ADR-0014: Dashboard Event-Driven + Standby Mode

## Contexto
O dashboard anterior utilizava polling fixo de 250ms para ler o estado do servidor do disco. Isso resultava em:
1.  Uso desnecessário de CPU e I/O mesmo quando o servidor estava ocioso.
2.  Dificuldade em distinguir entre um servidor ocioso e um servidor travado (crash).
3.  Falta de feedback visual sobre o nível de atividade real do servidor.

## Decisões

### 1. Arquitetura Orientada a Eventos
O dashboard agora utiliza a biblioteca `watchfiles` para reagir a mudanças no arquivo `dashboard_state.json`. 
-   O fetcher entra em modo bloqueante (com timeout de segurança) aguardando o evento de escrita do SO.
-   A frequência de atualização do dashboard passa a ser ditada pelo servidor (push-like behavior via disco).

### 2. Sistema de Refcount de Atividade
O `TelemetryWriter` no servidor implementa um contador de referência (`activity_count`).
-   Qualquer ferramenta MCP ou worker de background incrementa o contador ao iniciar e decrementa ao finalizar.
-   Isso permite que o servidor publique seu estado como `active`, `idle` ou `error`.

### 3. Heartbeat de 10 Segundos
Uma thread dedicada no servidor publica a telemetria a cada 10 segundos, mesmo sem atividade.
-   Permite que o dashboard detecte "Server Offline" se o timestamp for muito antigo (> 30s).
-   Mantém o dashboard "vivo" sem a necessidade de polling agressivo.

### 4. Feedback Visual (LEDs)
O dashboard utiliza um sistema de cores para representar o estado:
-   🟢 **Verde**: Servidor Ativo (processando ferramenta ou embed).
-   🟡 **Amarelo**: Standby (Servidor ligado mas ocioso).
-   🔴 **Vermelho**: Erro detectado na última operação.
-   ⚫ **Cinza**: Servidor Offline (Heartbeat expirado).

### 5. Spinner Condicional
O spinner de atividade (`⠋⠙⠹...`) agora só é exibido quando o estado é `active`. Em standby, ele é substituído por um ponto fixo (`·`), reduzindo a "poluição visual" e reforçando a sensação de ociosidade.

## Consequências
-   Redução significativa no uso de recursos do sistema quando o servidor está ocioso.
-   Melhor legibilidade do estado do agente (Agent Legibility).
-   Maior robustez na detecção de falhas do servidor.
