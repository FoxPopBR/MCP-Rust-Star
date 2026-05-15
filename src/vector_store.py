"""
VectorStore — ChromaDB com isolamento por projeto.

Cada project_id tem sua própria coleção ChromaDB independente.
Isso garante isolamento real: clear de um projeto não toca outro,
e é possível inspecionar o tamanho individual de cada base.

Convenção de nome de coleção: "proj_<project_id_normalizado>"
  ex: "Rust Star" → "proj_rust_star"
      "FoxOT"     → "proj_foxot"
"""

import re
import chromadb
import os
from dotenv import load_dotenv

load_dotenv()

from tools.logger import logger


def _collection_name(project_id: str) -> str:
    """Normaliza o project_id para um nome válido de coleção ChromaDB.
    ChromaDB exige: 3-63 chars, apenas [a-zA-Z0-9_-], não pode começar/terminar com ponto.
    """
    # Remove caracteres inválidos, substitui espaços por underscore
    clean = re.sub(r"[^a-zA-Z0-9_-]", "_", project_id.strip()).lower()
    # Remove underscores múltiplos
    clean = re.sub(r"_+", "_", clean).strip("_")
    name = f"proj_{clean}"
    # ChromaDB: mínimo 3 chars
    if len(name) < 3:
        name = name + "_kb"
    return name[:63]


class VectorStore:
    """
    Banco vetorial ChromaDB com uma coleção por projeto.

    Uso:
        db = VectorStore()
        db.add_document(id, embedding, doc, metadata, project_id="Rust Star")
        db.query(embedding, project_id="Rust Star")
    """

    def __init__(self):
        self.data_path = os.getenv("CHROMA_DATA_PATH", "./data/chroma")
        os.makedirs(self.data_path, exist_ok=True)
        try:
            self.client = chromadb.PersistentClient(path=self.data_path)
            logger.info(f"VectorStore (ChromaDB) inicializado em: {self.data_path}")
        except Exception as e:
            logger.error(f"Erro ao inicializar VectorStore: {str(e)}")
            raise

    def _get_collection(self, project_id: str):
        """Retorna (ou cria) a coleção isolada deste projeto."""
        name = _collection_name(project_id)
        return self.client.get_or_create_collection(name=name)

    def _all_collections(self) -> list:
        """Lista todas as coleções de projeto existentes (prefixo 'proj_')."""
        try:
            return [c for c in self.client.list_collections()
                    if c.name.startswith("proj_")]
        except Exception:
            return []

    # ─── Escrita ──────────────────────────────────────────────────────────────

    def add_document(
        self,
        id: str,
        embedding: list,
        document: str,
        metadata: dict,
        file_hash: str = None,
    ):
        """Adiciona um documento na coleção do projeto indicado em metadata['project_id']."""
        project_id = metadata.get("project_id", "default")
        try:
            if file_hash:
                metadata = {**metadata, "file_hash": file_hash}
            col = self._get_collection(project_id)
            col.add(
                ids=[id],
                embeddings=[embedding],
                documents=[document],
                metadatas=[metadata],
            )
            logger.debug(f"[{project_id}] Doc {id[:8]}… adicionado (hash={file_hash}).")
        except Exception as e:
            logger.error(f"Erro ao adicionar doc [{project_id}]: {str(e)}")
            raise

    # ─── Cache ────────────────────────────────────────────────────────────────

    def check_hash(self, file_hash: str, project_id: str) -> bool:
        """Retorna True se o arquivo (por hash MD5) já foi indexado neste projeto."""
        try:
            col = self._get_collection(project_id)
            results = col.get(
                where={"file_hash": {"$eq": file_hash}},
                limit=1,
                include=[],
            )
            return len(results.get("ids", [])) > 0
        except Exception as e:
            logger.debug(f"check_hash falhou para [{project_id}] (assume não indexado): {e}")
            return False

    # ─── Consulta ─────────────────────────────────────────────────────────────

    def query(self, embedding: list, project_id: str = None, n_results: int = 5) -> dict:
        """Busca documentos similares.

        - project_id informado → busca na coleção isolada daquele projeto.
        - project_id=None      → busca em TODOS os projetos e agrega os resultados.
        """
        if project_id:
            return self._query_single(embedding, project_id, n_results)
        else:
            return self._query_all(embedding, n_results)

    def _query_single(self, embedding: list, project_id: str, n_results: int) -> dict:
        """Consulta apenas a coleção do projeto informado."""
        try:
            col = self._get_collection(project_id)
            count = col.count()
            if count == 0:
                logger.warning(f"Coleção do projeto '{project_id}' está vazia.")
                return {"documents": [[]], "metadatas": [[]]}
            actual_n = min(n_results, count)
            results = col.query(query_embeddings=[embedding], n_results=actual_n)
            logger.debug(f"[{project_id}] {actual_n} resultados retornados.")
            return results
        except Exception as e:
            logger.error(f"Erro ao consultar [{project_id}]: {str(e)}")
            raise

    def _query_all(self, embedding: list, n_results: int) -> dict:
        """Consulta todas as coleções de projeto e agrega os top-N resultados globais."""
        try:
            all_docs = []
            all_metas = []
            all_distances = []

            for col_meta in self._all_collections():
                col = self.client.get_collection(col_meta.name)
                count = col.count()
                if count == 0:
                    continue
                actual_n = min(n_results, count)
                res = col.query(
                    query_embeddings=[embedding],
                    n_results=actual_n,
                    include=["documents", "metadatas", "distances"],
                )
                if res.get("documents") and res["documents"][0]:
                    all_docs.extend(res["documents"][0])
                    all_metas.extend(res["metadatas"][0] or [None] * len(res["documents"][0]))
                    all_distances.extend(res.get("distances", [[]])[0] or [1.0] * len(res["documents"][0]))

            if not all_docs:
                return {"documents": [[]], "metadatas": [[]]}

            combined = sorted(
                zip(all_distances, all_docs, all_metas),
                key=lambda x: x[0],
            )[:n_results]

            sorted_docs = [d for _, d, _ in combined]
            sorted_metas = [m for _, _, m in combined]

            logger.debug(f"[GLOBAL] {len(sorted_docs)} resultados de {len(self._all_collections())} projetos.")
            return {"documents": [sorted_docs], "metadatas": [sorted_metas]}

        except Exception as e:
            logger.error(f"Erro na consulta global: {str(e)}")
            raise

    # ─── Listagem ─────────────────────────────────────────────────────────────

    def list_sources(self, project_id: str = None) -> list:
        """Lista todos os arquivos únicos indexados, opcionalmente filtrado por projeto."""
        try:
            if project_id:
                cols_to_scan = [self._get_collection(project_id)]
            else:
                cols_to_scan = [
                    self.client.get_collection(c.name)
                    for c in self._all_collections()
                ]

            seen = set()
            sources = []
            for col in cols_to_scan:
                if col.count() == 0:
                    continue
                results = col.get(include=["metadatas"])
                for meta in (results.get("metadatas") or []):
                    if not meta:
                        continue
                    src = meta.get("source", "desconhecido")
                    proj = meta.get("project_id", "desconhecido")
                    key = (proj, src)
                    if key not in seen:
                        seen.add(key)
                        sources.append({"project_id": proj, "source": src})

            return sorted(sources, key=lambda x: (x["project_id"], x["source"]))
        except Exception as e:
            logger.error(f"Erro ao listar fontes: {str(e)}")
            return []

    def get_project_stats(self) -> dict:
        """Retorna estatísticas de cada projeto indexado (contagem de chunks)."""
        stats = {}
        for col_meta in self._all_collections():
            col = self.client.get_collection(col_meta.name)
            proj_name = col_meta.name.removeprefix("proj_")
            stats[proj_name] = {"chunks": col.count(), "collection": col_meta.name}
        return stats

    # ─── Limpeza ──────────────────────────────────────────────────────────────

    def delete_by_project(self, project_id: str) -> str:
        """Remove completamente a coleção de um projeto."""
        try:
            col_name = _collection_name(project_id)
            self.client.delete_collection(name=col_name)
            logger.info(f"Coleção '{col_name}' (projeto '{project_id}') removida.")
            return f"Projeto '{project_id}' removido da base de conhecimento."
        except Exception as e:
            logger.error(f"Erro ao remover projeto '{project_id}': {str(e)}")
            raise

    def clear(self) -> str:
        """Remove TODAS as coleções de projeto."""
        try:
            cols = self._all_collections()
            for col_meta in cols:
                self.client.delete_collection(name=col_meta.name)
            logger.warning(f"Todas as coleções removidas: {[c.name for c in cols]}")
            return f"Base de dados completa limpa ({len(cols)} projetos removidos)."
        except Exception as e:
            logger.error(f"Erro ao limpar base de dados: {str(e)}")
            raise
