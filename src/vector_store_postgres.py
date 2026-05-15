import psycopg2
from pgvector.psycopg2 import register_vector
import os
import json
from tools.logger import logger

class PostgresStore:
    def __init__(self):
        self.host = os.getenv("POSTGRES_HOST", "localhost")
        self.port = os.getenv("POSTGRES_PORT", "5432")
        self.db_name = os.getenv("POSTGRES_DB", "mcp_knowledge")
        self.user = os.getenv("POSTGRES_USER", "user")
        self.password = os.getenv("POSTGRES_PASSWORD", "password")
        self.conn = None
        self._init_db()

    def _get_connection(self):
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.db_name,
                user=self.user,
                password=self.password
            )
            self.conn.autocommit = True
            
            # Garante que a extensão existe ANTES de registrar o tipo no driver
            with self.conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            register_vector(self.conn)
        return self.conn

    def _init_db(self):
        """Inicializa a tabela de embeddings."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                # Cria a tabela de conhecimento
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                        id UUID PRIMARY KEY,
                        project_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        embedding vector(2560),
                        metadata JSONB,
                        file_hash TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                # NOTA: O pgvector v0.5+ e versões anteriores têm limite de 2000 dimensões para índices HNSW/IVFFlat.
                # Como o Qwen usa 2560 dimensões, usaremos busca exata (sem índice) por enquanto para garantir precisão total.
                # Para projetos de médio porte, a diferença de performance é imperceptível.
            logger.info("PostgresStore inicializado com busca exata (Sem índice vetorial para >2000 dimensões).")
        except Exception as e:
            logger.error(f"Erro ao inicializar PostgresStore: {str(e)}")
            raise

    def add_document(self, id: str, embedding: list, document: str, metadata: dict, file_hash: str = None):
        """Adiciona um documento ao PostgreSQL com suporte a hash de integridade."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO knowledge_embeddings (id, project_id, content, embedding, metadata, file_hash) VALUES (%s, %s, %s, %s, %s, %s)",
                    (id, metadata.get('project_id'), document, embedding, json.dumps(metadata), file_hash)
                )
            logger.debug(f"Documento {id} adicionado ao Postgres (Hash: {file_hash}).")
        except Exception as e:
            logger.error(f"Erro ao adicionar documento ao Postgres: {str(e)}")
            raise

    def check_hash(self, file_hash: str, project_id: str) -> bool:
        """Verifica se um arquivo com este hash já foi indexado para este projeto."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM knowledge_embeddings WHERE file_hash = %s AND project_id = %s LIMIT 1",
                    (file_hash, project_id)
                )
                return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Erro ao verificar hash: {str(e)}")
            return False

    def query(self, embedding: list, project_id: str = None, n_results: int = 3):
        """Busca documentos similares usando busca vetorial do pgvector."""
        try:
            import numpy as np
            # Converte para array numpy para garantir compatibilidade com pgvector
            emb_array = np.array(embedding)
            
            conn = self._get_connection()
            with conn.cursor() as cur:
                if project_id:
                    cur.execute(
                        "SELECT content, metadata FROM knowledge_embeddings WHERE project_id = %s ORDER BY embedding <=> %s LIMIT %s",
                        (project_id, emb_array, n_results)
                    )
                else:
                    cur.execute(
                        "SELECT content, metadata FROM knowledge_embeddings ORDER BY embedding <=> %s LIMIT %s",
                        (emb_array, n_results)
                    )
                
                rows = cur.fetchall()
                # Formata no estilo do ChromaDB para compatibilidade
                results = {
                    'documents': [[row[0] for row in rows]],
                    'metadatas': [[row[1] for row in rows]]
                }
                return results
        except Exception as e:
            logger.error(f"Erro ao consultar PostgresStore: {str(e)}")
            raise

    def delete_by_project(self, project_id: str):
        """Remove todos os dados de um projeto."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("DELETE FROM knowledge_embeddings WHERE project_id = %s", (project_id,))
            logger.info(f"Dados do projeto '{project_id}' removidos do Postgres.")
            return f"Dados do projeto '{project_id}' removidos."
        except Exception as e:
            logger.error(f"Erro ao remover projeto do Postgres: {str(e)}")
            raise

    def clear(self):
        """Limpa toda a tabela."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE knowledge_embeddings;")
            logger.warning("Tabela knowledge_embeddings limpa no Postgres.")
            return "Base de dados completa limpa."
        except Exception as e:
            logger.error(f"Erro ao limpar Postgres: {str(e)}")
            raise
