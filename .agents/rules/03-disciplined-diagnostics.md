# Regra 03: Loop de Diagnóstico Disciplinado

Bugs no MCP Rust Star não são "corrigidos", eles são "aniquilados" através de um processo científico.

## 1. A Sequência Obrigatória
NUNCA tente uma correção sem passar por estas 6 etapas:

1.  **Reproduzir**: Crie um script ou comando que falhe consistentemente.
2.  **Minimizar**: Reduza o código ao menor snippet possível que ainda apresente o erro.
3.  **Hipotetizar**: Declare formalmente o que você acha que está quebrado e por quê.
4.  **Instrumentar**: Use o `logger` de `tools.logger` para adicionar telemetria (nível DEBUG) e validar sua hipótese.
5.  **Corrigir**: Aplique a mudança cirúrgica.
6.  **Teste de Regressão**: Execute o passo 1 novamente para garantir que passou e verifique se funcionalidades correlatas ainda funcionam.

## 2. Proibição de "Tentativa e Erro"
Alterar o código "para ver se funciona" é uma violação desta regra. Toda mudança deve ser baseada em evidência capturada via `stderr` ou logs.

## 3. Documentação de Causa Raiz
Se o bug for complexo, a causa raiz deve ser documentada em uma nova Skill ou ADR para que o sistema aprenda com o erro.
