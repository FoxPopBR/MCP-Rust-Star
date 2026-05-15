# Skill: Práticas de Engenharia de Elite (Matt Pocock Style)

Esta skill ensina como aplicar filosofias de engenharia de alto nível no contexto do servidor MCP Rust Star.

## 1. Aplicação da Linguagem Ubíqua
Ao receber um comando vago, use o `CONTEXT.md` para traduzir o desejo do usuário em termos técnicos precisos.
- **Ação**: Se o usuário diz "arruma o banco", você pergunta: "Você se refere a limpar a coleção do ChromaDB para o projeto FoxOT ou otimizar a persistência em `data/`?"

## 2. Execução da Sabatina (Grilling)
Sempre que uma nova funcionalidade for solicitada:
1.  Pare e pense.
2.  Liste 3 perguntas críticas sobre estados de erro e limites de escopo.
3.  Aguarde o alinhamento antes de codificar.

## 3. Operação do Loop de Diagnóstico
Ao encontrar um erro de conexão com o Ollama ou falha no ChromaDB:
- Não "chute" a solução.
- Aumente o nível do `logger` para DEBUG.
- Capture a saída do `stderr`.
- Identifique o ponto exato da falha na stack trace antes de propor o `replace`.

## 4. Gestão de ADRs
Ao sugerir uma mudança (ex: "vamos usar FastAPI"), crie automaticamente o rascunho do ADR em `docs/adr/` explicando o raciocínio. Isso evita que o projeto se torne uma colcha de retalhos de decisões esquecidas.
