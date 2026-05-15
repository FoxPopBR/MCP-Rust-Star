import chromadb
import os
from dotenv import load_dotenv

load_dotenv()

from tools.logger import logger

class VectorStore:
    def __init__(self):
        self.data_path = os.getenv("CHROMA_DATA_PATH", "./data")
        try:
            self.client = chromadb.PersistentClient(path=self.data_path)
            self.collection = self.client.get_or_create_collection(name="rust_star_knowledge")
            logger.info(f"VectorStore inicializado com persistência em: {self.data_path}")
        except Exception as e:
            logger.error(f"Erro ao inicializar VectorStore: {str(e)}")
            raise

    def add_document(self, id: str, embedding: list, document: str, metadata: dict):
        """Adiciona um documento e seu embedding ao banco."""
        try:
            self.collection.add(
                ids=[id],
                embeddings=[embedding],
                documents=[document],
                metadatas=[metadata]
            )
            logger.debug(f"Documento {id} adicionado à coleção.")
        except Exception as e:
            logger.error(f"Erro ao adicionar documento {id}: {str(e)}")
            raise

    def query(self, embedding: list, project_id: str = None, n_results: int = 3):
        """Busca documentos similares baseado no embedding da query, filtrando por projeto."""
        try:
            where_filter = {"project_id": project_id} if project_id else None
            logger.debug(f"Executando query com filtro project_id: {project_id}")
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=n_results,
                where=where_filter
            )
            return results
        except Exception as e:
            logger.error(f"Erro ao consultar VectorStore: {str(e)}")
            raise

    def delete_by_project(self, project_id: str):
        """Remove todos os documentos associados a um projeto específico."""
        try:
            self.collection.delete(where={"project_id": project_id})
            logger.info(f"Dados do projeto '{project_id}' removidos com sucesso.")
            return f"Dados do projeto '{project_id}' removidos."
        except Exception as e:
            logger.error(f"Erro ao remover dados do projeto '{project_id}': {str(e)}")
            raise

    def clear(self):
        """Remove todos os documentos da coleção."""
        try:
            self.client.delete_collection(name="rust_star_knowledge")
            self.collection = self.client.get_or_create_collection(name="rust_star_knowledge")
            logger.warning("Toda a base de conhecimento foi limpa.")
            return "Base de dados completa limpa."
        except Exception as e:
            logger.error(f"Erro ao limpar base de dados: {str(e)}")
            raise
