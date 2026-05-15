# ADR 0005: Migração para PostgreSQL + pgvector e Persistência Industrial

- **Status**: Aceito
- **Data**: 15/05/2026
- **Autor**: Antigravity

## Contexto
O sistema utilizava anteriormente o ChromaDB (ou soluções em memória) para armazenamento vetorial. Embora funcional para protótipos, esta abordagem apresentava riscos de corrupção de dados sob carga massiva (como os 10k arquivos do FoxOT), falta de transacionalidade ACID e dificuldade em gerenciar o isolamento estrito de múltiplos projetos em larga escala.

## Decisão
Migrar a camada de persistência para o **PostgreSQL** utilizando a extensão **pgvector**. 
- Implementar o padrão de tabelas dinâmicas (`knowledge_[project_id]`) para garantir isolamento físico dos dados.
- Utilizar o driver `psycopg2-binary` para comunicação de alta performance.

## Consequências
- **Positivas**: 
    - Estabilidade industrial para indexação de dezenas de milhares de arquivos.
    - Suporte nativo a transações SQL.
    - Facilidade de manutenção e limpeza seletiva de bases de conhecimento.
- **Negativas**: 
    - Aumento leve na complexidade do setup (exigência de Docker/Postgres).
    - Necessidade de gerenciar conexões persistentes.
