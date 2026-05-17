# Diagnóstico: Implementação do Sistema LLMLAB no MCP Rust Star

> **Data**: 16/05/2026
> **Objetivo**: Analisar o projeto LLMLAB e diagnosticar como adaptar seu sistema de Agentic Engineering para o MCP Rust Star.

---

## 1. Resumo do LLMLAB — O Que Ele É

O LLMLAB é um **template de Agentic Engineering** — não é um produto funcional, é um **meta-sistema** para governar como IAs operam em repositórios. Ele materializa práticas de 6 referências da indústria (Anthropic, OpenAI, Martin Fowler, TLC, Matt Pocock, GSD-2) em arquivos concretos:

| Componente | Função |
|---|---|
| **4 Skills** (`.agents/skills/`) | Personas multi-agente: Planner → Executor → Evaluator → Harness Engineer |
| **GEMINI.md** | Harness global — regras de comportamento do agente |
| **CONTEXT.md** | Linguagem ubíqua com proibição de sinônimos |
| **verify.ps1** | Verification Ladder — escada de verificação determinística |
| **.specs/** | Sprint Contracts (`spec.md`, `design.md`, `tasks.md`) + STATE.md (memória) |
| **STUDY/** | Base teórica com deep dives das 6 referências |

---

## 2. Comparativo: LLMLAB vs MCP Rust Star (Estado Atual)

| Dimensão | LLMLAB | MCP Rust Star | Gap |
|---|---|---|---|
| **Skills multi-agente** | 4 skills bem definidas (Planner, Executor, Evaluator, Harness Engineer) | 16 skills (mistura de engenharia + operação do servidor) | MCP Rust Star tem mais skills mas sem a separação clara de personas |
| **GEMINI.md** | Focado em Agentic Engineering puro | Focado em operação do servidor RAG | Diferentes propósitos — complementares |
| **CONTEXT.md** | Ontologia estrita de Agentic Engineering (Skill, Harness, Verification Ladder, Sprint Contract) | Ontologia de domínio (Rust Star, FoxOT, FoxClient, Embedding, RAG) | Diferentes domínios — não conflitam |
| **Verification Ladder** | `verify.ps1` — script PowerShell com 4 etapas de validação | `pytest` — sem script unificado de verificação | **Gap crítico** — Rust Star não tem verification ladder unificada |
| **Sprint Contracts** | `.specs/features/` com `spec.md`, `design.md`, `tasks.md` | Não existe | **Gap crítico** — Rust Star não tem processo spec-driven formal |
| **STATE.md** | Memória contínua do projeto | `docs/SESSION_LOG.md` (equivalente) | **Parcial** — SESSION_LOG cumpre papel similar |
| **STUDY/** | 6 deep dives + database de conhecimento | Não existe | **Gap** — Rust Star não tem base teórica documentada |
| **Sceptic Evaluator** | Skill dedicada para QA rigoroso | Não existe | **Gap** — Rust Star não tem papel de avaliador independente |

---

## 3. O Que Vale a Pena Trazer (Priorizado)

### 🔴 Alta Prioridade — Impacto Imediato

#### 3.1 Verification Ladder Unificada (`verify.ps1`)

**Problema atual**: Rust Star roda `pytest` mas não tem um script único que valide lint → typecheck → testes → execução do servidor.

**Solução**: Criar `verify.ps1` na raiz do Rust Star:

```powershell
# [1/5] Static Analysis
python -m py_compile src/main.py src/services/*.py tools/logger.py

# [2/5] Type Check (se houver mypy configurado)
# python -m mypy src/

# [3/5] Unit Tests
pytest tests/ -v

# [4/5] Server Health Check
python -c "from src.services.rag_service import RAGService; print('OK')"

# [5/5] Dashboard Import Check
python -c "from dashboard.app import main; print('OK')"
```

**Por que importa**: Garante que qualquer agente declare "tarefa concluída" apenas após evidência empírica, não "parece correto".

#### 3.2 Sprint Contracts (`.specs/features/`)

**Problema atual**: Features são implementadas direto no código sem especificação formal. O SESSION_LOG registra depois, não antes.

**Solução**: Adotar o fluxo do `spec-driven-planner`:
- Features médias → `.specs/features/<nome>/spec.md` (objetivo + critérios de aceite)
- Features grandes → tríade `spec.md` + `design.md` + `tasks.md`

**Por que importa**: Evita "vibe coding" e garante que tarefas caibam numa janela de contexto.

#### 3.3 Sceptic Evaluator

**Problema atual**: Não há papel de QA independente. O agente que escreve o código é o mesmo que "aprova".

**Solução**: Copiar/adaptar `.agents/skills/sceptic-evaluator/SKILL.md` do LLMLAB.

**Por que importa**: LLMs são lenientes com o próprio trabalho. Um avaliador separado pega violações que o executor ignora.

---

### 🟡 Média Prioridade — Melhoria de Processo

#### 3.4 STATE.md como Memória Contínua

**Situação atual**: `docs/SESSION_LOG.md` já faz papel similar, mas é um diário narrativo longo.

**Solução**: Criar `.specs/project/STATE.md` conciso ao lado do SESSION_LOG:
- STATUS: verde/amarelo/vermelho
- Último marco concluído
- Bloqueios ativos
- Próximo passo imediato

**Por que importa**: Mais rápido de ler que o SESSION_LOG inteiro para um agente que retoma sessão.

#### 3.5 STUDY/ — Base Teórica

**Situação atual**: Rust Star tem regras (`.agents/rules/`) mas não tem base teórica documentada.

**Solução**: Copiar os 6 deep dives do LLMLAB para `docs/STUDY/` do Rust Star (ou referenciar o LLMLAB diretamente).

**Por que importa**: Quando o agente enfrenta dilema arquitetural, tem referência para consultar em vez de inventar.

#### 3.6 Auto-Sizing no Fluxo de Trabalho

**Conceito do LLMLAB**: Classificar pedidos em Small/Medium/Large/Complex e aplicar workflow diferente.

**Solução**: Adicionar ao `AGENTS.md` ou criar skill `auto-sizer`:
- Small (≤3 arquivos) → codar direto
- Medium (<10 tasks) → spec.md
- Large (multi-componente) → spec + design + tasks
- Complex (ambíguo) → interview loop primeiro

---

### 🟢 Baixa Prioridade — Nice to Have

#### 3.7 Context Reset Formal

**Situação atual**: SESSION_LOG já serve como "farol" para próxima sessão.

**Solução**: Formalizar o protocolo: ao completar marco complexo, atualizar STATE.md + sugerir nova conversa.

#### 3.8 Agent Legibility nos Erros

**Conceito do LLMLAB**: Mensagens de erro devem incluir dicas acionáveis para outra IA consertar.

**Solução**: Adotar como convenção no `tools/logger.py` — erros já são bons, mas podem incluir "Para corrigir: tente X".

---

## 4. O Que NÃO Trazer (e Por Quê)

| Componente LLMLAB | Motivo para não trazer |
|---|---|
| **Sinônimos proibidos do CONTEXT.md** | Os termos do LLMLAB (Verification Ladder, Harness, Sprint Contract) são de Agentic Engineering genérico. O Rust Star já tem sua ontologia de domínio em `CONTEXT.md`. Podem coexistir sem conflito. |
| **Separação rígida Planner → Executor → Evaluator** | O Rust Star tem 16 skills especializadas que já cobrem essas personas de forma mais granular. Forçar a tríade seria redundante. |
| **csv_reader.py / simulações** | É código de exemplo do LLMLAB, não tem relação com RAG/MCP. |
| **GEMINI.md do LLMLAB** | O Rust Star já tem seu próprio GEMINI.md focado em operação do servidor. Fundir os dois criaria confusão. |

---

## 5. Plano de Implementação Sugerido

### Fase 1 — Foundation (1 sessão)
1. Criar `verify.ps1` com 4-5 etapas de validação
2. Copiar `sceptic-evaluator/SKILL.md` para `.agents/skills/`
3. Adicionar seção de Auto-Sizing ao `AGENTS.md`

### Fase 2 — Spec-Driven (1-2 sessões)
4. Criar estrutura `.specs/features/` e `.specs/project/`
5. Criar template de `spec.md`, `design.md`, `tasks.md`
6. Criar `STATE.md` em `.specs/project/`

### Fase 3 — Knowledge Base (1 sessão)
7. Copiar deep dives do `STUDY/` do LLMLAB para `docs/STUDY/` do Rust Star
8. Atualizar `AGENTS.md` para referenciar os STUDY docs quando relevante

### Fase 4 — Refinamento (contínuo)
9. Formalizar Context Reset no SESSION_LOG
10. Melhorar Agent Legibility nos logs de erro

---

## 6. Conclusão

O LLMLAB é um **meta-sistema de governança de agentes**, enquanto o MCP Rust Star é um **produto funcional com seu próprio sistema de regras**. Eles não competem — **complementam**.

O maior gap é a **ausência de Verification Ladder unificada** e **processo spec-driven formal**. São os dois itens que mais impactam a qualidade do código produzido por IAs.

A boa notícia: o Rust Star já tem a infraestrutura mais madura (regras 00-06, 16 skills, SESSION_LOG, ADRs, EventBus, ModelGuard). O LLMLAB traz disciplina de processo que o Rust Star ainda não formalizou.

**Recomendação**: Começar pela Fase 1 (verify.ps1 + sceptic-evaluator + auto-sizing). São mudanças de baixo risco e alto impacto imediato.
