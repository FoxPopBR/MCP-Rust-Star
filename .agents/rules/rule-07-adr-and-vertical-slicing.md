# Regra 07: ADRs, Alinhamento e Fatiamento Vertical

Seguindo as melhores práticas de engenharia de elite, o MCP Rust Star adota uma abordagem disciplinada para decisões e implementação.

## 1. Architecture Decision Records (ADRs)
Toda decisão arquitetural significativa (ex: troca de banco de dados, mudança no protocolo de comunicação, adoção de novo modelo LLM) deve ser documentada em `docs/adr/`.
- **Formato**: Contexto, Decisão, Consequências (Positivas e Negativas).
- **Objetivo**: Fornecer rastreabilidade do "porquê" para futuros desenvolvedores e agentes de IA.

## 2. O Protocolo de "Grilling" (Sabatina)
Antes de iniciar uma implementação complexa, o agente DEVE questionar o usuário ou a si mesmo sobre:
- Premissas ocultas.
- Casos de borda (edge cases).
- Validação de inputs e estados de erro de APIs externas (Ollama/ChromaDB).
- Impacto na VRAM e performance do RAG.

## 3. Fatiamento Vertical (Vertical Slicing)
Não tente construir funcionalidades gigantes de uma vez.
- **Abordagem**: Divida a tarefa em fatias funcionais de ponta a ponta (ex: em vez de "Criar sistema de arquivos", comece com "Implementar leitura de arquivo único com logs").
- **Benefício**: Ciclos de feedback mais rápidos e código mais testável.

## 4. Diagnóstico Disciplinado
NUNCA aplique uma correção sem antes:
1.  **Reproduzir**: Confirmar o bug de forma consistente.
2.  **Minimizar**: Isolar o problema no menor contexto possível.
3.  **Hipotetizar**: Explicar a causa raiz provável.
4.  **Instrumentar**: Adicionar logs (`logger`) para validar a hipótese.
5.  **Corrigir e Validar**: Aplicar a solução e garantir que o bug foi eliminado sem regressões.
