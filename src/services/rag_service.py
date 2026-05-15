import uuid
import os
from src.ollama_client import OllamaClient
from src.vector_store_postgres import PostgresStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.config_manager import ConfigManager

from tools.logger import logger

# Separadores específicos por linguagem de programação.
# A ordem importa: tenta dividir nos pontos mais "semânticos" primeiro.
_LANG_SEPARATORS = {
    # Rust: divide em funções, impl blocks, structs, enums, traits, mods
    "rs": [
        "\npub fn ", "\nfn ", "\npub async fn ", "\nasync fn ",
        "\nimpl ", "\npub impl ", "\ntrait ", "\npub trait ",
        "\nstruct ", "\npub struct ", "\nenum ", "\npub enum ",
        "\nmod ", "\npub mod ", "\ntype ", "\nconst ",
        "\n\n", "\n", " ", "",
    ],
    # C/C++: divide em funções, classes, namespaces, structs
    "cpp": [
        "\nvoid ", "\nint ", "\nbool ", "\nauto ",
        "\nclass ", "\nstruct ", "\nnamespace ", "\ntemplate ",
        "\ninline ", "\nstatic ", "\nvirtual ", "\noverride ",
        "\n\n", "\n", " ", "",
    ],
    "c": [
        "\nvoid ", "\nint ", "\nbool ", "\nstruct ",
        "\ntypedef ", "\n#define ", "\n\n", "\n", " ", "",
    ],
    "h": [
        "\nclass ", "\nstruct ", "\nnamespace ", "\n#define ",
        "\n\n", "\n", " ", "",
    ],
    "hpp": [
        "\nclass ", "\nstruct ", "\nnamespace ", "\ntemplate ",
        "\n\n", "\n", " ", "",
    ],
    # Lua: divide em funções e blocos
    "lua": [
        "\nfunction ", "\nlocal function ", "\nlocal ",
        "\nif ", "\nfor ", "\nwhile ", "\n\n", "\n", " ", "",
    ],
    # Python: divide em classes e funções
    "py": [
        "\nclass ", "\ndef ", "\nasync def ",
        "\n\n", "\n", " ", "",
    ],
    # Markdown e docs: divide em seções
    "md": ["\n## ", "\n### ", "\n#### ", "\n\n", "\n", " ", ""],
    "txt": ["\n\n", "\n", " ", ""],
    # Protobuf
    "proto": ["\nmessage ", "\nenum ", "\nservice ", "\n\n", "\n", " ", ""],
    # TOML / configuração
    "toml": ["\n[", "\n\n", "\n", " ", ""],
}

# Padrão genérico para extensões não mapeadas
_DEFAULT_SEPARATORS = ["\n\n", "\n", " ", ""]


def _get_separators_for_file(file_path: str) -> list:
    """Retorna separadores de chunking otimizados para a linguagem do arquivo."""
    ext = os.path.splitext(file_path)[1].lstrip(".").lower()
    return _LANG_SEPARATORS.get(ext, _DEFAULT_SEPARATORS)


class RAGService:
    def __init__(self):
        self.ollama = OllamaClient()
        self.config = ConfigManager()
        settings = self.config.get_all()

        # Banco de dados: sempre PostgreSQL.
        self.db = PostgresStore()
        self.store_type = "postgres"

        indexing_cfg = settings.get("indexing", {})
        chunk_size = indexing_cfg.get("chunk_size", 12000)
        chunk_overlap = indexing_cfg.get("chunk_overlap", 1000)

        # Text splitter base (usado para docs e linguagens sem separador específico)
        self._base_chunk_size = chunk_size
        self._base_chunk_overlap = chunk_overlap

        logger.info(
            f"RAGService inicializado | Store: {self.store_type.upper()} | "
            f"Chunk: {chunk_size} chars / Overlap: {chunk_overlap} chars"
        )

    def _get_splitter(self, file_path: str = None) -> RecursiveCharacterTextSplitter:
        """Retorna um splitter otimizado para a linguagem do arquivo."""
        separators = _get_separators_for_file(file_path) if file_path else _DEFAULT_SEPARATORS
        return RecursiveCharacterTextSplitter(
            chunk_size=self._base_chunk_size,
            chunk_overlap=self._base_chunk_overlap,
            separators=separators,
        )

    def index_text(
        self,
        text: str,
        project_id: str,
        source: str = "manual",
        file_hash: str = None,
        session_active: bool = False,
        file_path: str = None,
    ) -> str:
        """Divide o texto em chunks, gera embeddings e salva no banco.

        Args:
            session_active: Se True, mantém modelos na VRAM (modo batch).
            file_path: Caminho do arquivo original para seleção de separadores.
        """
        try:
            if not text.strip():
                logger.warning(f"Texto vazio ignorado para {source}")
                return "Aviso: Conteúdo vazio não indexado."

            # Verificação de cache por hash MD5
            if file_hash and hasattr(self.db, "check_hash"):
                if self.db.check_hash(file_hash, project_id):
                    logger.info(f"Cache Hit: {source} inalterado. Pulando.")
                    return "Cache Hit: Arquivo já indexado."

            logger.info(f"Indexando: {source} (Projeto: {project_id})")

            splitter = self._get_splitter(file_path or source)
            chunks = splitter.split_text(text)
            total = len(chunks)
            logger.info(f"Dividido em {total} fragmentos ({os.path.splitext(source or '')[1] or 'texto'}).")

            for i, chunk in enumerate(chunks):
                is_last = i == total - 1
                # Em modo sessão batch, só descarrega na chamada final
                should_unload = (not session_active) and is_last

                embedding = self.ollama.get_embedding(chunk, auto_unload=should_unload)
                doc_id = str(uuid.uuid4())
                metadata = {
                    "source": source,
                    "project_id": project_id,
                    "chunk_index": i,
                    "total_chunks": total,
                }
                self.db.add_document(doc_id, embedding, chunk, metadata, file_hash=file_hash)

            return f"{total} fragmentos indexados com sucesso de '{source}'."

        except Exception as e:
            logger.error(f"Erro ao indexar texto de {source}: {str(e)}")
            raise

    def index_file_by_path(self, file_path: str, project_id: str, session_active: bool = False) -> str:
        """Lê o arquivo, calcula MD5 e indexa se o conteúdo mudou desde a última indexação."""
        try:
            import hashlib
            ext = os.path.splitext(file_path)[1].lower().lstrip(".")

            with open(file_path, "rb") as f:
                content_bytes = f.read()

            file_hash = hashlib.md5(content_bytes).hexdigest()

            if ext == "pdf":
                text = self._extract_text_from_pdf(file_path)
            else:
                text = content_bytes.decode("utf-8", errors="replace")

            return self.index_text(
                text,
                project_id,
                source=file_path,
                file_hash=file_hash,
                session_active=session_active,
                file_path=file_path,
            )
        except Exception as e:
            logger.error(f"Erro ao ler arquivo {file_path}: {str(e)}")
            raise

    def _extract_text_from_pdf(self, file_path: str) -> str:
        """Extrai texto de um PDF usando pypdf."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            pages = [p.extract_text() for p in reader.pages if p.extract_text()]
            return "\n".join(pages)
        except Exception as e:
            logger.error(f"Falha na extração do PDF {file_path}: {str(e)}")
            return ""

    def index_image(self, file_path: str, project_id: str) -> str:
        """Usa Vision para descrever a imagem e indexa o texto com metadados de origem."""
        try:
            abs_path = os.path.abspath(file_path)
            file_name = os.path.basename(file_path)

            description = self.ollama.describe_image(abs_path)
            if not description:
                return "Erro: Não foi possível gerar descrição para a imagem."

            # Injeta metadados de origem no texto para melhorar busca semântica futura
            enhanced_text = (
                f"ORIGEM VISUAL: {file_name}\n"
                f"LOCALIZAÇÃO: {abs_path}\n"
                f"PROJETO: {project_id}\n\n"
                f"DESCRIÇÃO TÉCNICA:\n{description}"
            )

            return self.index_text(enhanced_text, project_id, source=abs_path)
        except Exception as e:
            logger.error(f"Erro ao indexar imagem {file_path}: {str(e)}")
            raise

    def search_and_generate(self, question: str, project_id: str = None) -> dict:
        """Busca contexto relevante e gera resposta usando RAG filtrado por projeto."""
        try:
            target_label = project_id if project_id else "GLOBAL (Todos os Projetos)"
            logger.info(f"Iniciando busca RAG: '{question[:60]}...' | Escopo: {target_label}")

            query_embedding = self.ollama.get_embedding(question)

            settings = self.config.get_all()
            n_results = settings.get("rag", {}).get("n_results", 5)
            search_results = self.db.query(query_embedding, project_id=project_id, n_results=n_results)

            contexts = []
            if search_results and "documents" in search_results and search_results["documents"]:
                contexts = search_results["documents"][0]

            # Inclui metadados de fonte para citação
            sources_meta = []
            if search_results and "metadatas" in search_results and search_results["metadatas"]:
                sources_meta = search_results["metadatas"][0] or []

            # Monta contexto com atribuição de fonte
            context_parts = []
            for i, (ctx, meta) in enumerate(zip(contexts, sources_meta)):
                src = meta.get("source", "desconhecido") if meta else "desconhecido"
                proj = meta.get("project_id", "") if meta else ""
                header = f"[Fonte {i+1}: {os.path.basename(src)} | Projeto: {proj}]"
                context_parts.append(f"{header}\n{ctx}")

            context_str = "\n\n".join(context_parts)

            if not contexts:
                logger.warning(f"Nenhum contexto encontrado para: {target_label}")
            else:
                logger.info(f"{len(contexts)} fragmentos recuperados.")

            answer = self.ollama.generate_response(question, context_str, project_id=project_id)

            return {
                "answer": answer,
                "context_used": contexts,
                "sources": sources_meta,
                "project_id": project_id,
            }
        except Exception as e:
            logger.error(f"Falha crítica no pipeline RAG: {str(e)}")
            raise

    def list_indexed_sources(self, project_id: str = None) -> list:
        """Lista todos os arquivos únicos indexados no banco."""
        try:
            if hasattr(self.db, "list_sources"):
                return self.db.list_sources(project_id)
            return []
        except Exception as e:
            logger.error(f"Erro ao listar fontes: {str(e)}")
            return []

    def clear_database(self, project_id: str = None) -> str:
        """Limpa a base de dados, opcionalmente filtrada por projeto."""
        if project_id:
            logger.info(f"Limpando base de dados do projeto: {project_id}")
            return self.db.delete_by_project(project_id)
        else:
            logger.warning("Limpando TODA a base de dados vetorial.")
            return self.db.clear()
