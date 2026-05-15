# Regra 04: Fatiamento Vertical e ADRs

Grandes mudanças devem ser fatiadas e justificadas para manter a velocidade e a qualidade.

## 1. Fatiamento Vertical (Vertical Slicing)
Implemente funcionalidades de ponta a ponta em fatias finas.
- **Errado**: "Criar todo o sistema de banco de dados".
- **Certo**: "Implementar a ferramenta de deleção por projeto (ID) com logs e persistência".
Cada fatia deve ser funcional, testável e entregar valor imediato ao workspace.

## 2. Architecture Decision Records (ADRs)
Toda decisão técnica que mude a trajetória do projeto deve ser gravada em `docs/adr/`.
- **Formato**:
    - **Contexto**: O problema ou oportunidade.
    - **Decisão**: A escolha feita (ex: Usar `qwen3.5:4b` em vez de `9b`).
    - **Consequências**: O que ganhamos e o que perdemos (VRAM, Latência, Precisão).

## 3. Isolamento de Domínio
Ao fatiar, garanta que o isolamento entre *Rust Star*, *FoxOT* e *FoxClient* seja mantido. Uma fatia vertical não deve "vazar" dados entre projetos.
