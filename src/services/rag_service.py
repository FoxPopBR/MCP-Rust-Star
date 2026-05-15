import uuid
import os
from src.ollama_client import OllamaClient
from src.vector_store import VectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.config_manager import ConfigManager

from tools.logger import logger

class RAGService:
    def __init__(self):
        import os
        self.ollama = OllamaClient()
        self.config = ConfigManager()
        settings = self.config.get_all()
        
        # Escolha do provedor de banco de dados
        store_type = os.getenv("VECTOR_STORE_TYPE", settings.get("vector_store", "chroma")).lower()
        if store_type == "postgres":
            from src.vector_store_postgres import PostgresStore
            self.db = PostgresStore()
        else:
            from src.vector_store import VectorStore
            self.db = VectorStore()
            
        # Configuração de Chunking baseada nas configurações
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.get("chunk_size", 12000),
            chunk_overlap=settings.get("chunk_overlap", 1000),
            separators=["\n\n", "\n", " ", ""]
        )
        logger.info(f"RAGService inicializado com {store_type.upper()} e {settings.get('chunk_size')} chunks.")

    def index_text(self, text: str, project_id: str, source: str = "manual", file_hash: str = None, session_active: bool = False):
        """Fatias o texto, gera embeddings e salva no banco. session_active controla o unload de VRAM."""
        try:
            if not text.strip():
                logger.warning(f"Texto vazio ignorado para {source}")
                return "Aviso: Conteúdo vazio não indexado."
                
            # Verifica cache se houver hash
            if file_hash and hasattr(self.db, 'check_hash'):
                if self.db.check_hash(file_hash, project_id):
                    logger.info(f"Cache Hit: Arquivo {source} inalterado. Pulando indexação.")
                    return "Cache Hit: Arquivo já indexado."

            logger.info(f"Iniciando indexação: {source} (Projeto: {project_id})")
            
            # Divide o texto em fragmentos inteligentes
            chunks = self.text_splitter.split_text(text)
            logger.info(f"Texto dividido em {len(chunks)} fragmentos.")
            
            for i, chunk in enumerate(chunks):
                logger.debug(f"Processando fragmento {i+1}/{len(chunks)}...")
                # Se estivermos em uma sessão (lote), não descarregamos a cada chunk
                # Descarregamos apenas se for o último chunk da última chamada ou se auto_unload=True
                should_unload = (not session_active) and (i == len(chunks) - 1)
                
                embedding = self.ollama.get_embedding(chunk, auto_unload=should_unload)
                doc_id = str(uuid.uuid4())
                metadata = {
                    "source": source, 
                    "project_id": project_id, 
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                }
                # Adiciona suporte a hash no DB
                if hasattr(self.db, 'add_document'):
                    import inspect
                    sig = inspect.signature(self.db.add_document)
                    if 'file_hash' in sig.parameters:
                        self.db.add_document(doc_id, embedding, chunk, metadata, file_hash=file_hash)
                    else:
                        self.db.add_document(doc_id, embedding, chunk, metadata)
            
            return f"{len(chunks)} fragmentos indexados com sucesso."
        except Exception as e:
            logger.error(f"Erro ao indexar texto no RAGService: {str(e)}")
            raise

    def index_file_by_path(self, file_path: str, project_id: str, session_active: bool = False):
        """Lê o arquivo, calcula MD5 e indexa se necessário."""
        try:
            import hashlib
            ext = file_path.lower().split('.')[-1]
            
            # Lê conteúdo binário para hash MD5
            with open(file_path, "rb") as f:
                content_bytes = f.read()
            file_hash = hashlib.md5(content_bytes).hexdigest()
            
            if ext == 'pdf':
                text = self._extract_text_from_pdf(file_path)
            else:
                text = content_bytes.decode('utf-8', errors='replace')
            
            return self.index_text(text, project_id, source=file_path, file_hash=file_hash, session_active=session_active)
        except Exception as e:
            logger.error(f"Erro ao ler arquivo {file_path}: {str(e)}")
            raise

    def _extract_text_from_pdf(self, file_path: str) -> str:
        """Extrai texto de um arquivo PDF usando pypdf."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            text = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
            return "\n".join(text)
        except Exception as e:
            logger.error(f"Falha na extração do PDF {file_path}: {str(e)}")
            return ""

    def index_image(self, file_path: str, project_id: str):
        """Usa o modelo Vision para descrever a imagem e indexa o texto resultante com metadados de origem."""
        try:
            abs_path = os.path.abspath(file_path)
            file_name = os.path.basename(file_path)
            
            description = self.ollama.describe_image(abs_path)
            if not description:
                return "Erro: Não foi possível gerar uma descrição para a imagem."
            
            # Injeta informações de origem no texto para busca semântica
            enhanced_text = f"""ORIGEM VISUAL: {file_name}
LOCALIZAÇÃO: {abs_path}
PROJETO: {project_id}

DESCRIÇÃO TÉCNICA:
{description}"""
            
            return self.index_text(enhanced_text, project_id, source=abs_path)
        except Exception as e:
            logger.error(f"Erro ao indexar imagem {file_path}: {str(e)}")
            raise

    def search_and_generate(self, question: str, project_id: str = None):
        """Busca contexto e gera uma resposta usando RAG, filtrando por projeto."""
        try:
            target_label = project_id if project_id else "GLOBAL (Todos os Projetos)"
            logger.info(f"Iniciando busca RAG para: {target_label}")
            
            query_embedding = self.ollama.get_embedding(question)
            # Recuperamos até 5 fragmentos para aproveitar o contexto de 16k do LLM
            search_results = self.db.query(query_embedding, project_id=project_id, n_results=5)
            
            contexts = []
            if search_results and 'documents' in search_results and search_results['documents']:
                contexts = search_results['documents'][0]
            
            context_str = "\n---\n".join(contexts) if contexts else ""
            
            if not contexts:
                logger.warning(f"Nenhum contexto relevante encontrado para a pergunta no escopo: {target_label}")
            else:
                logger.info(f"Contexto recuperado: {len(contexts)} fragmentos encontrados.")
            
            answer = self.ollama.generate_response(question, context_str, project_id=project_id)
            
            return {
                "answer": answer,
                "context_used": contexts,
                "project_id": project_id
            }
        except Exception as e:
            logger.error(f"Falha crítica no pipeline RAG: {str(e)}")
            raise

    def clear_database(self, project_id: str = None):
        """Limpa a base de dados, opcionalmente filtrada por projeto."""
        if project_id:
            logger.info(f"Limpando base de dados para o projeto: {project_id}")
            return self.db.delete_by_project(project_id)
        else:
            logger.warning("Limpando TODA a base de dados vetorial.")
            return self.db.clear()
