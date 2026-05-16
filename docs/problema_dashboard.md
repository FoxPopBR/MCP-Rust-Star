Avaliação da situação do problema atual feito por 3 modelos de i.a diferente


1) PRIMEIRA AVALIAÇÃO
Implementação de Telemetria de Alta Fidelidade e Resiliência do Dashboard
Este plano visa resolver o congelamento crítico do Dashboard e a fragilidade do sistema de telemetria atual, substituindo a comunicação via arquivos (lenta e propensa a locks no Windows) por um barramento de dados em memória via HTTP Local.

User Review Required
IMPORTANT

Nova Porta de Rede: O servidor MCP abrirá a porta TCP 12288 (configurável via .env) apenas para localhost. O usuário deve permitir a conexão se o Firewall do Windows solicitar. Abstração de I/O: A leitura direta de current_indexing.json pelo Dashboard será desativada em favor da API, mas a escrita no arquivo pelo servidor será mantida (de forma atômica) para persistência e debug offline.

Open Questions
Qual o intervalo de atualização desejado para o Dashboard? (Atualmente 4 FPS / 250ms). Proponho manter 4 FPS para economizar CPU, mas com animações interpoladas se necessário.
Proposed Changes
1. Núcleo do Servidor (Telemetria em Memória)
[MODIFY] 
src/main.py
Implementar TelemetryService: Uma classe baseada em http.server.BaseHTTPRequestHandler rodando em uma thread daemon.
Endpoint /status: Retornará um merge de _embed_state (indexação) e rag.state (serviço).
Endpoint /health: Simples heartbeat para o Dashboard validar se o servidor está vivo.
[MODIFY] 
src/services/rag_service.py
Escrita Atômica: Alterar _persist_state para usar o padrão write to .tmp -> os.replace.
Throttling: Implementar um cooldown de 500ms para gravações físicas no disco, mantendo atualizações em memória instantâneas.
2. Infraestrutura do Dashboard
[MODIFY] 
dashboard/fetcher.py
Migração para HTTP: Substituir a lógica de _read_json por requisições urllib.request para localhost:12288/status.
Resiliência a Timeouts: Implementar timeout de 500ms e retry exponencial.
Estado de Desconexão: Adicionar flag connected ao self._data para que a UI possa exibir um modo "Offline" em vez de travar.
3. Interface de Usuário (Rich App)
[MODIFY] 
dashboard/app.py
Visual Heartbeat: Criar um componente no header que oscila (ex: um símbolo de sinal de satélite) a cada frame de renderização, provando que a UI não está travada.
Async-like Update: Garantir que o app.update() nunca bloqueie a renderização, mesmo se o fetcher estiver aguardando rede.
Handling de Redimensionamento: Validar o suporte ao alternate buffer (screen=True) e adicionar tratamento explícito de exceções no loop Live.
Verification Plan
Automated Tests
Script em scratch/test_telemetry.py para simular 100 requisições simultâneas ao endpoint de status e validar o tempo de resposta (alvo: < 5ms).
Validação de integridade do JSON após interrupção abrupta da escrita.
Manual Verification
Iniciar o Servidor MCP.
Iniciar o Dashboard.
Verificar se o redimensionamento da janela do terminal é instantâneo.
Fechar o servidor MCP (Ctrl+C) e observar o Dashboard entrar em modo "RECONNECTING" sem congelar a aplicação.



2) SEGUNDA AVALIAÇÃO

# ADR-0012: Post-Mortem — Dashboard "carrega imagem inicial e trava"

## Status
Diagnóstico concluído (16/05/2026). Fix proposto, **aguardando aprovação** antes de aplicar em `dashboard/app.py`.

## Sintoma reportado

O dashboard exibe o frame inicial e nunca mais atualiza. Relógio do header, contadores de stats, painel de progresso, fila de logs — nada muda visualmente, mesmo com o servidor ativo escrevendo `data/current_indexing.json` e `logs/mcp_error.log`.

Reincidência: terceira vez no ciclo 2026-05-15/16 (ver `feedback_dashboard_principles.md`). As duas primeiras foram causa diferente (file-lock contention com `mcp_error.log`). Esta é causa nova.

## Diagnóstico (skill `diagnose`)

### Phase 1 — Feedback loop
Harness descartável `tools/diag_live_freeze.py` reproduz o sintoma em isolamento total:
- Instancia `rich.live.Live` com a mesma configuração do dashboard
- Captura bytes emitidos ao "stdout" (na verdade `io.StringIO`) em 3 frames consecutivos
- Pass/fail determinístico em ~2 segundos
- Comparação de 3 cenários numa única corrida: config atual, fix-A, fix-B

### Phase 2 — Repro
RUN A (config atual): `(0, 0, 0)` bytes emitidos entre frames. **Bug 100% reproduzível.**

### Phase 3 — Hipóteses (resumo, detalhes na conversa)
- **H1 (Rich Live não repinta sem refresh)** — CONFIRMADA pelo harness
- H2 (KeyError em painel inventário) — falsificada (harness não usa painel inventário)
- H3 (DataFetcher segura lock) — falsificada (harness não usa DataFetcher)
- H4 (contenção com `mcp_error.log`) — irrelevante para este sintoma
- H5 (`time.sleep` capturado por OS scheduling) — falsificada

### Phase 4 — Instrumentação
Harness substitui logs ad-hoc: sinal binário objetivo, sem ambiguidade.

## Causa raiz

`dashboard/app.py:591`:
```python
with Live(initial, screen=True, auto_refresh=False) as live:
    while True:
        live.update(app.update())          # <- NÃO repinta
        time.sleep(0.25)
```

`rich.live.Live` separa "trocar o renderable" (`.update()`) de "emitir bytes ao stdout" (`.refresh()`). Com `auto_refresh=False` e sem `live.refresh()` (nem `update(..., refresh=True)`), o alternate-screen recebe apenas o frame emitido pelo `__enter__` do context manager. Todos os `update()` subsequentes mutam estado interno do Rich mas não fazem repaint.

Documentação Rich: `auto_refresh=True` é o default precisamente porque o uso típico assume repaint automático em background via thread daemon `_RefreshThread`. Foi `auto_refresh=False` desligado provavelmente para "evitar contenção" — uma otimização sem efeito real que quebrou o caso de uso.

## Decisão (proposta, **não aplicada**)

**Fix A — recomendado:**
```python
with Live(initial, screen=True, auto_refresh=True, refresh_per_second=4, console=console) as live:
    while not stop_event.is_set():
        live.update(app.update())
        stop_event.wait(0.25)
```

Rationale:
- Rich gerencia o repaint em thread daemon a 4 Hz independente do polling
- Resolve a queixa colateral "relógio só anda no ritmo do polling"
- Mantém custo de CPU baixo (alternate-screen + 4 fps + diff interno do Rich)
- `stop_event.wait()` em vez de `time.sleep()` permite shutdown limpo

**Fix B — alternativa:** manter `auto_refresh=False` e adicionar `live.refresh()` após cada `update`. Mais previsível, mais código, sem ganho real.

## Regression test

`tools/diag_live_freeze.py` vira `tests/dashboard/test_live_repaints.py` com assertions pytest. ~10 linhas de adaptação. Trava CI se alguém reintroduzir `auto_refresh=False` sem refresh manual.

## Consequências

- **Positivas:**
  - Dashboard volta a renderizar a 4 Hz autonomamente, mesmo se DataFetcher trava
  - Relógio, logs e stats atualizam sem depender de polling de JSON
  - Regression test impede reincidência
  - Princípio "dashboard não pode atrapalhar o servidor" preservado (sem novo IO)

- **Riscos:**
  - `_RefreshThread` do Rich é mais um daemon. Já temos 2 do DataFetcher → total 3. Aceitável.
  - Se o renderable produzido por `app.update()` levantar exceção, com `auto_refresh=True` o Rich pode reportar de forma diferente. Mantém o `try/except` envolvendo `live.update()`.

## O que teria prevenido isso

Regression test desde o início. O dashboard nunca teve teste de render — só de unidades isoladas. A skill `diagnose` Phase 6 pergunta "what would have prevented this bug?" — resposta: um teste headless que mediria bytes emitidos em N frames. Exatamente o `tools/diag_live_freeze.py`. Promovê-lo a teste permanente fecha o ciclo.

## Cleanup

Pós-aplicação do fix:
- [ ] Migrar `tools/diag_live_freeze.py` para `tests/dashboard/test_live_repaints.py`
- [ ] Deletar `tools/diag_live_freeze.py`
- [ ] Commit message cita H1 confirmada para o próximo debugger
- [ ] Atualizar memória `feedback_dashboard_principles.md` com a regra: "Rich `Live` no dashboard SEMPRE `auto_refresh=True` ou chamar `refresh()` explicitamente."




3) TERCEIRA AVALIAÇÃO

# Diagnóstico: Congelamento do Dashboard de Telemetria

**Data:** 16/05/2026
**Objetivo:** Analisar travamentos e a viabilidade da via atual de telemetria baseada em "Shared State".

## 1. Comportamento em Estado Ocioso (AFK)
Quando o servidor de conhecimento não está processando arquivos (estado AFK), a telemetria não pausa. O arquivo `fetcher.py` roda em *loop* ininterrupto, abrindo e lendo o arquivo `data/current_indexing.json` do disco a uma frequência de 4Hz (4 vezes por segundo), além de executar requisições HTTP para o serviço Ollama a cada 2 segundos.
**Diagnóstico:** Desperdício de I/O em disco e ciclos de CPU lendo informações que não sofreram mutação.

## 2. Inicialização, Threads e Loop de Renderização
- **Bloqueio de Inicialização:** A inicialização do Dashboard aguarda obrigatoriamente a primeira varredura completa do disco (`while not fetcher.ready`). O aplicativo só mostra a primeira tela após o disco responder.
- **Gerenciamento de Tela:** Existe uma `Main Thread` exclusiva cuidando da interface com a biblioteca `rich`. As coletas de telemetria ocorrem em *threads daemon* separadas.
- **Renderização (Gargalo de FPS):** A aplicação **não roda a 30 FPS**. O laço de repetição (`app.py`, linha ~589) possui uma trava estática de processamento `time.sleep(0.25)`. A interface desenha no máximo 4 frames por segundo.
- **Causa do Travamento Visual:** Ao configurar a biblioteca `rich` com `auto_refresh=False` e operar o loop da tela a míseros 4 FPS sem invocar um comando explícito de redesenho da tela de console, os eventos do sistema operacional (como alterar o tamanho da janela do terminal) não são processados. O Dashboard congela visualmente na geometria original.

## 3. A solicitação de telemetria está travando o dashboard?
**Não de forma síncrona.**
Analisando a proteção de memória (`_lock` no `fetcher.py`), a operação custosa de ler o arquivo físico no disco é feita **fora** da trava de memória.
Isso significa que, mesmo que o sistema de arquivos fique estrangulado tentando ler o JSON, a *Thread* de interface gráfica (que apenas consome a versão em memória via `fetcher.get()`) não ficará travada esperando o disco.
**Conclusão:** O travamento total (interface irresponsiva) é uma falha na lógica de renderização e configuração da UI no terminal, não no volume de telemetria processado pelo `fetcher`.

## 4. O Problema da Arquitetura "Shared State" (JSON no disco)
Embora a interface não trave por causa da leitura do disco, **a sua premissa arquitetural está correta: a via atual é frágil e propensa a erros de colisão.**
Uma arquitetura onde um servidor faz `json.dump` repetidamente enquanto um cliente tenta ler simultaneamente a 4Hz resulta em problemas mecânicos:
- Erros silenciosos de quebra de JSON (tentar ler o arquivo no exato momento da escrita corrompe o buffer).
- Enfileiramento de I/O a nível de Sistema Operacional Windows.
- Impossibilidade de escalar a taxa de atualização (FPS) da telemetria sem massacrar o disco SSD do usuário.
A telemetria, de fato, deve ser transmitida pronta através de um fluxo dedicado de memória ou rede.
