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
            with self.conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            register_vector(self.conn)
        return self.conn

    def _init_db(self):
        """Inicializa a tabela de embeddings."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
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
                    (id, metadata.get("project_id"), document, embedding, json.dumps(metadata), file_hash)
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
            emb_array = np.array(embedding)
            conn = self._get_connection()
            with conn.cursor() as cur:
                if project_id:
                    cur.execute(
                        "SELECT content, metadata FROM knowledge_embeddings "
                        "WHERE project_id = %s ORDER BY embedding <=> %s LIMIT %s",
                        (project_id, emb_array, n_results)
                    )
                else:
                    cur.execute(
                        "SELECT content, metadata FROM knowledge_embeddings "
                        "ORDER BY embedding <=> %s LIMIT %s",
                        (emb_array, n_results)
                    )
                rows = cur.fetchall()
                # psycopg2 pode retornar JSONB como string ou dict dependendo do driver.
                # Normalizamos explicitamente para garantir dict sempre.
                def _to_dict(v):
                    if isinstance(v, str):
                        try:
                            return json.loads(v)
                        except Exception:
                            return {}
                    return v if isinstance(v, dict) else {}
                return {
                    "documents": [[row[0] for row in rows]],
                    "metadatas": [[_to_dict(row[1]) for row in rows]],
                }
        except Exception as e:
            logger.error(f"Erro ao consultar PostgresStore: {str(e)}")
            raise

    def list_sources(self, project_id: str = None) -> list:
        """Lista todos os arquivos únicos indexados, opcionalmente filtrado por projeto."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                if project_id:
                    cur.execute(
                        "SELECT DISTINCT project_id, metadata->>'source' AS source "
                        "FROM knowledge_embeddings WHERE project_id = %s ORDER BY source",
                        (project_id,)
                    )
                else:
                    cur.execute(
                        "SELECT DISTINCT project_id, metadata->>'source' AS source "
                        "FROM knowledge_embeddings ORDER BY project_id, source"
                    )
                rows = cur.fetchall()
                return [{"project_id": r[0], "source": r[1] or "desconhecido"} for r in rows]
        except Exception as e:
            logger.error(f"Erro ao listar fontes no Postgres: {str(e)}")
            return []

    def delete_by_project(self, project_id: str):
        """Remove todos os dados de um projeto."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM knowledge_embeddings WHERE project_id = %s",
                    (project_id,)
                )
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
