import psycopg2
from psycopg2 import pool
from pgvector.psycopg2 import register_vector
import os
import json
import re
from dotenv import load_dotenv

load_dotenv(override=True)
from collections import Counter
from tools.logger import logger

class PostgresStore:
    def __init__(self):
        self.host = os.getenv("POSTGRES_HOST", "localhost")
        self.port = os.getenv("POSTGRES_PORT", "5432")
        self.db_name = os.getenv("POSTGRES_DB", "mcp_knowledge")
        self.user = os.getenv("POSTGRES_USER", "user")
        self.password = os.getenv("POSTGRES_PASSWORD", "password")
        self.embedding_dim = int(os.getenv("EMBEDDING_DIM", "2560"))
        self._pool = None
        self._init_db()

    def _init_db(self):
        """Inicializa o pool de conexões com timeouts e extensões básicas."""
        try:
            # connect_timeout: 10s para estabelecer conexão
            # options: configurações de keepalive para detectar queda de link
            conn_params = {
                "host": self.host,
                "port": self.port,
                "database": self.db_name,
                "user": self.user,
                "password": self.password,
                "connect_timeout": 10,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5
            }
            
            self._pool = psycopg2.pool.SimpleConnectionPool(
                1, 15,  # Aumentado para 15 conexões
                **conn_params
            )
            
            # Garante que a extensão vector existe
            conn = self._pool.getconn()
            conn.autocommit = True
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                register_vector(conn)
            finally:
                self._pool.putconn(conn)
                
            logger.info("PostgresStore inicializado com Pool de Conexões (1-10).")
        except Exception as e:
            logger.error(f"Erro ao inicializar PostgresStore: {str(e)}")
            raise

    def _get_conn(self):
        """Obtém uma conexão do pool e registra o tipo vector."""
        conn = self._pool.getconn()
        conn.autocommit = True
        try:
            # Sempre registra para garantir que a conexão atual conheça o tipo
            register_vector(conn)
        except:
            pass
        return conn

    def _release_conn(self, conn):
        """Retorna a conexão ao pool."""
        self._pool.putconn(conn)

    def _get_table_name(self, project_id: str) -> str:
        if not project_id:
            return "knowledge_global"
        slug = re.sub(r'[^a-zA-Z0-9_]', '_', project_id.lower())
        return f"knowledge_{slug}"[:63]

    def _get_all_tables(self) -> list:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'knowledge_%';")
                return [row[0] for row in cur.fetchall()]
        finally:
            self._release_conn(conn)

    def _ensure_table(self, table_name: str):
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table_name} (
                        id UUID PRIMARY KEY,
                        content TEXT NOT NULL,
                        embedding vector({self.embedding_dim}),
                        metadata JSONB,
                        category TEXT,
                        tags JSONB,
                        file_hash TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
        finally:
            self._release_conn(conn)

    def add_document(self, id: str, embedding: list, document: str, metadata: dict, file_hash: str = None):
        """Adiciona um documento à tabela isolada do projeto com suporte a hash de integridade."""
        try:
            safe_document = document.replace('\x00', '')
            project_id = metadata.get("project_id", "global")
            table_name = self._get_table_name(project_id)
            self._ensure_table(table_name)
            
            category = metadata.get("category", "others")
            tags = metadata.get("tags", [])
            
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"INSERT INTO {table_name} (id, content, embedding, metadata, category, tags, file_hash) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (id, safe_document, embedding, json.dumps(metadata), category, json.dumps(tags), file_hash)
                    )
            finally:
                self._release_conn(conn)
            logger.debug(f"Documento {id} adicionado ao Postgres em {table_name} (Hash: {file_hash}).")
        except Exception as e:
            logger.error(f"Erro ao adicionar documento ao Postgres: {str(e)}")
            raise

    def check_hash(self, file_hash: str, project_id: str) -> bool:
        """Verifica se um arquivo com este hash já foi indexado."""
        try:
            table_name = self._get_table_name(project_id)
            self._ensure_table(table_name)
            
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT 1 FROM {table_name} WHERE file_hash = %s LIMIT 1",
                        (file_hash,)
                    )
                    return cur.fetchone() is not None
            finally:
                self._release_conn(conn)
        except Exception as e:
            logger.error(f"Erro ao verificar hash: {str(e)}")
            return False

    def search(self, embedding: list, project_id: str = None, n_results: int = 3):
        """Busca documentos similares usando pgvector."""
        try:
            import numpy as np
            emb_array = np.array(embedding)
            
            tables = [self._get_table_name(project_id)] if project_id else self._get_all_tables()
            if not tables:
                return []
            
            if project_id:
                self._ensure_table(tables[0])
            
            union_queries = []
            for t in tables:
                union_queries.append(f"(SELECT content, metadata, embedding <=> %s AS distance FROM {t})")
            
            final_query = " UNION ALL ".join(union_queries) + " ORDER BY distance ASC LIMIT %s"
            params = [emb_array] * len(tables) + [n_results]
            
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(final_query, params)
                    rows = cur.fetchall()
                    
                    def _to_dict(v):
                        if isinstance(v, str):
                            try: return json.loads(v)
                            except: return {}
                        return v if isinstance(v, dict) else {}
                        
                    results = []
                    for row in rows:
                        results.append({
                            "content": row[0],
                            "metadata": _to_dict(row[1]),
                            "distance": float(row[2])
                        })
                    return results
            finally:
                self._release_conn(conn)
        except Exception as e:
            logger.error(f"Erro ao consultar PostgresStore: {str(e)}")
            raise

    def get_inventory_stats(self, project_id: str = None) -> list:
        """Retorna estatísticas de (project_id, file_count, fragment_count, extensions_stats)."""
        try:
            tables = [self._get_table_name(project_id)] if project_id else self._get_all_tables()
            if not tables:
                return []
                
            results = []
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    for t in tables:
                        # 1. Total de fragmentos
                        cur.execute(f"SELECT COUNT(*) FROM {t}")
                        frag_count = cur.fetchone()[0]
                        
                        # 2. Total de arquivos únicos e estatísticas de extensão
                        # Usamos metadata->>'source' para identificar arquivos
                        cur.execute(f"""
                            SELECT 
                                metadata->>'project_id' as pid,
                                metadata->>'source' as src
                            FROM {t}
                            GROUP BY pid, src
                        """)
                        rows = cur.fetchall()
                        
                        file_count = len(rows)
                        ext_counter = Counter()
                        actual_pid = project_id or "global"
                        
                        for r_pid, r_src in rows:
                            if r_pid: actual_pid = r_pid
                            ext = os.path.splitext(r_src or "")[1].lower() or "(sem-ext)"
                            ext_counter[ext] += 1
                            
                        results.append({
                            "project_id": actual_pid,
                            "file_count": file_count,
                            "frag_count": frag_count,
                            "extensions": dict(ext_counter)
                        })
            finally:
                self._release_conn(conn)
            
            return sorted(results, key=lambda x: x["project_id"])
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas do inventário: {str(e)}")
            return []

    def list_sources(self, project_id: str = None) -> list:
        """Lista todos os arquivos únicos indexados."""
        try:
            tables = [self._get_table_name(project_id)] if project_id else self._get_all_tables()
            if not tables:
                return []
                
            if project_id:
                self._ensure_table(tables[0])
            
            results = []
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    for t in tables:
                        cur.execute(
                            f"SELECT DISTINCT metadata->>'project_id' AS project_id, metadata->>'source' AS source FROM {t}"
                        )
                        rows = cur.fetchall()
                        for r in rows:
                            results.append({"project_id": r[0] or "desconhecido", "source": r[1] or "desconhecido"})
            finally:
                self._release_conn(conn)
            
            unique_results = {f"{r['project_id']}::{r['source']}": r for r in results}
            return sorted(list(unique_results.values()), key=lambda x: (x["project_id"], x["source"]))
        except Exception as e:
            logger.error(f"Erro ao listar fontes no Postgres: {str(e)}")
            return []

    def delete_by_project(self, project_id: str):
        """Remove todos os dados de um projeto."""
        try:
            table_name = self._get_table_name(project_id)
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {table_name};")
            finally:
                self._release_conn(conn)
            logger.info(f"Tabela do projeto '{project_id}' removida.")
            return f"Dados do projeto '{project_id}' removidos."
        except Exception as e:
            logger.error(f"Erro ao remover projeto do Postgres: {str(e)}")
            raise

    def clear(self):
        """Limpa toda a base."""
        try:
            tables = self._get_all_tables()
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    for t in tables:
                        cur.execute(f"DROP TABLE IF EXISTS {t};")
            finally:
                self._release_conn(conn)
            logger.warning("Todas as tabelas foram limpas.")
            return "Base de dados completa limpa."
        except Exception as e:
            logger.error(f"Erro ao limpar Postgres: {str(e)}")
            raise
