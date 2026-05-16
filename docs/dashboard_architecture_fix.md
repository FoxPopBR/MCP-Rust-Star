# Plano Técnico e Arquitetural: Resolução de Congelamento e Telemetria do Dashboard

**Objetivo:** Eliminar o congelamento da interface do Dashboard e substituir a frágil arquitetura de "Shared State" (JSON em disco) por uma via de telemetria mais profunda e resiliente, utilizando o vocabulário arquitetural do projeto.

---

## O Problema Arquitetural

Após analisar o código (`dashboard/app.py`, `dashboard/fetcher.py` e `src/main.py`) e a documentação fornecida, fica claro que enfrentamos problemas devido a **Interfaces rasas (shallow interfaces)** e **vazamento de implementações pela costura (seam)**. 

Os problemas dividem-se em dois eixos:

1. **Fricção 1: Costura de Telemetria Rasi (Shared State via Disco)**
   O servidor MCP atualiza seu estado escrevendo ativamente um arquivo JSON (`data/current_indexing.json`) no disco. O Dashboard, através do adaptador `DataFetcher`, faz o *polling* contínuo (4Hz) desse arquivo.
   - **Problema:** Esta é uma **Interface extremamente rasa**. A complexidade do I/O, os bloqueios de arquivo e a latência de disco vazam pela **seam** (costura) que divide o servidor e o cliente. Isso cria fragilidade mecânica e impossibilita escalar a taxa de atualização sem massacrar o hardware (SSD).

2. **Fricção 2: Falta de Profundidade no Render Loop da Interface Gráfica**
   No `dashboard/app.py`, a renderização utiliza a biblioteca `rich.live.Live` configurada com `auto_refresh=False`. 
   - **Problema:** Ao desligar a atualização automática, a responsabilidade de emitir os bytes (o *repaint* na tela) passa para o laço de controle principal, mas o código atual chama apenas `live.update()` (que altera o estado interno) sem chamar `live.refresh()` (que pinta na tela). O terminal fica congelado visualmente na geometria original porque não há repintura contínua independente do *polling* de dados. A interface do `Live` foi subutilizada, tornando o módulo da UI **shallow**.

---

## Oportunidades de Aprofundamento (Deepening Opportunities)

Abaixo, os candidatos de refatoração para resolver a arquitetura atual:

### Candidato 1: Aprofundar a Costura de Telemetria com Adaptador HTTP Local
- **Files:** `src/main.py` (ou novo arquivo de serviço de telemetria), `dashboard/fetcher.py`.
- **Problem:** O acoplamento via disco (Shared State) gera gargalos de I/O e fragilidade na sincronização entre o servidor MCP e o dashboard.
- **Solution:** Criar uma nova **Seam** de comunicação usando HTTP Local. O servidor MCP irá manter o estado de telemetria em memória e expor um endpoint (ex: `localhost:12288/status`) usando uma *thread daemon*. O adaptador `DataFetcher` será modificado para consumir esta **Interface** HTTP em vez de ler do disco. A persistência no disco do servidor MCP será tratada de forma assíncrona ou em intervalos maiores apenas para *logs/crash dumps*, removendo-a do caminho crítico da telemetria.
- **Benefits:**
  - **Locality:** A lógica de estado em tempo real fica encapsulada na memória do servidor MCP.
  - **Leverage:** O adaptador HTTP oferece alta confiabilidade e tempo de resposta (< 5ms) para o Dashboard sem risco de *file-lock contention* no Windows.

### Candidato 2: Delegar o Repaint para a Interface `Live` (Aumentar a Profundidade do Render)
- **Files:** `dashboard/app.py`.
- **Problem:** O loop principal do aplicativo tenta gerenciar o tempo (*sleep* de 0.25) e a atualização de dados, mas falha em repintar a tela (`refresh`).
- **Solution:** Aprofundar o uso do módulo `Live` ativando `auto_refresh=True` e definindo `refresh_per_second=4`. O loop principal da aplicação focará apenas em fornecer novos dados de estado (`live.update()`) quando necessário. Se os dados não chegarem ou a thread de requisição travar, o adaptador `Live` ainda manterá sua própria *thread* de repintura ativa, garantindo que a tela responda a redimensionamentos e não trave visualmente.
- **Benefits:**
  - **Locality:** O gerenciamento do terminal alternativo (alternate screen) e taxa de atualização (FPS) é isolado dentro da biblioteca `rich`.
  - **Leverage:** Com uma mudança pequena na interface, ganhamos a capacidade de manter a UI responsiva de maneira assíncrona, mesmo quando o `DataFetcher` estiver ocioso ou esperando uma rede com lag. Testes futuros poderão validar a renderização contínua sem depender do fluxo de dados.

---

## Plano de Execução

1. **Passo 1 (UI - Correção Imediata do Congelamento):**
   - Modificar `dashboard/app.py` para alterar o gerenciador de contexto `Live(initial, screen=True, auto_refresh=True, refresh_per_second=4)`.
   - Substituir o uso perigoso de `time.sleep(0.25)` por uma forma limpa que seja interrompível, garantindo o funcionamento do relógio sem depender da chegada de novos dados.
2. **Passo 2 (Backend - Novo Adaptador de Telemetria):**
   - Adicionar uma classe de telemetria `TelemetryService` em `src/main.py` rodando via *http.server* para expor a variável `_embed_state` na porta definida.
3. **Passo 3 (Frontend - Consumidor HTTP):**
   - Refatorar o `dashboard/fetcher.py` para realizar `urllib.request` no novo endpoint de telemetria no lugar da leitura em disco do JSON. Manter um padrão resiliente de *timeouts* e retentativas (retry) curtas.

**Aguardando confirmação:** Gostaria de proceder com as refatorações sugeridas nestes candidatos? Posso iniciar com o **Passo 1** para restaurar a integridade visual da UI.