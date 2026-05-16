import os
import uuid
import hashlib
from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.vector_store_postgres import PostgresStore
from src.ollama_client import OllamaClient
from src.config_manager import ConfigManager
from tools.logger import logger


class RAGService:
    def __init__(self):
        self.config = ConfigManager()
        self.store_type = os.getenv("VECTOR_STORE", "postgres")
        self.db = PostgresStore()
        self.ollama = OllamaClient()
        
        # Estado para monitoramento (Dashboard)
        self.state = {
            "stats": {"new": 0, "cached": 0, "skipped": 0, "errors": 0},
            "current_file": "",
            "current_folder": "",
            "project_id": ""
        }

        # Callback opcional disparado após cada mutação de estado.
        # main.py atribui um publisher de telemetria aqui.
        self._on_state_change = None

        # Configuração de chunking
        settings = self.config.get_all().get("indexing", {})
        self.chunk_size = settings.get("chunk_size", int(os.getenv("CHUNK_SIZE", "8000")))
        self.chunk_overlap = settings.get("chunk_overlap", int(os.getenv("CHUNK_OVERLAP", "1000")))
        
        logger.info(f"RAGService inicializado | Store: {self.store_type.upper()} | Chunk: {self.chunk_size} chars / Overlap: {self.chunk_overlap} chars")
        self._persist_state()

    def _persist_state(self):
        """Notifica o observador (telemetry writer) com o estado atual.

        A persistência em disco agora é responsabilidade exclusiva do
        TelemetryWriter, que publica o snapshot unificado em
        `data/dashboard_state.json`. Aqui só disparamos o callback.
        """
        if self._on_state_change is not None:
            try:
                self._on_state_change()
            except Exception:
                pass

    def update_state(self, **kwargs):
        """Atualiza o estado e persiste no disco."""
        if "stats_inc" in kwargs:
            inc = kwargs.pop("stats_inc")
            for key, val in inc.items():
                self.state["stats"][key] = self.state["stats"].get(key, 0) + val
        
        self.state.update(kwargs)
        self._persist_state()

    def _get_splitter(self, file_path: str):
        """Retorna o splitter adequado baseado na extensão do arquivo."""
        ext = os.path.splitext(file_path)[1].lower() if file_path else ""
        
        separators = None
        if ext in {".rs"}:
            separators = ["\nfn ", "\nimpl ", "\nstruct ", "\nenum ", "\ntrait ", "\nmod ", "\n\n", "\n", " "]
        elif ext in {".c", ".cpp", ".h", ".hpp"}:
            separators = ["\nclass ", "\nstruct ", "\nvoid ", "\nint ", "\nnamespace ", "\n\n", "\n", " "]
        elif ext in {".lua"}:
            separators = ["\nfunction ", "\nlocal function ", "\n\n", "\n", " "]
        elif ext in {".py"}:
            separators = ["\ndef ", "\nclass ", "\n\n", "\n", " "]
        elif ext in {".json"}:
            separators = ["\n  },", "\n  {", "\n],", "\n[", "\n\n", "\n", " "]

        return RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=separators,
            keep_separator=True
        )
        
    def _get_category(self, file_path: str) -> str:
        """Determina a categoria baseada no caminho (Elite Mapping + Dynamic Fallback)."""
        if not file_path:
            return "others"
            
        path_lower = file_path.lower().replace("\\", "/")
        
        # 1. Elite Mapping (Sinais Fortes de Arquitetura)
        elite_map = {
            # FoxOT / OpenTibia
            "/npc/": "npc",
            "/monster/": "monster",
            "/spells/": "spell",
            "/actions/": "action",
            "/movements/": "movement",
            "/lib/": "lib",
            "/scripts/": "script",
            
            # FoxClient
            "/modules/": "client_module",
            "/data/": "client_data",
            
            # Rust Star (Engine)
            "/client/": "engine_client",
            "/server/": "engine_server",
            "/shared/": "engine_shared",
            "/proto/": "protocol",
            
            # Global / Infra
            "/engine/": "engine",
            "/src/": "engine",
            "/docs/": "docs",
            "/config/": "config",
            "/assets/": "assets",
            "/tools/": "tools"
        }
        
        for pattern, cat in elite_map.items():
            if pattern in path_lower:
                return cat
                
        # 2. Dynamic Fallback (Pasta pai imediata)
        parts = [p for p in path_lower.split("/") if p]
        if len(parts) > 1:
            # Pega o nome da pasta pai do arquivo
            return parts[-2]
            
        return "others"

    def _get_tags(self, file_path: str) -> list:
        """Extrai tags semânticas da hierarquia de pastas."""
        if not file_path:
            return []
            
        path_norm = file_path.replace("\\", "/")
        parts = [p for p in path_norm.split("/") if p]
        
        # Filtra partes irrelevantes (como letras de drive no Windows ou caminhos de sistema)
        # Mantém apenas as últimas 4 partes (contexto local)
        ignored = {"c:", "phantasy", "users", "appdata", "local", "temp"}
        tags = [p for p in parts if p.lower() not in ignored and len(p) > 1]
        
        return tags[-5:] # Retorna no máximo as últimas 5 partes do caminho como tags

    def _calculate_md5(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def index_text(self, text: str, source: str, project_id: str, file_path: str = None, session_active: bool = False) -> str:
        """Divide o texto em chunks e indexa no banco de dados.
        Se o embedding de um chunk falhar, tenta subdividi-lo em pedaços menores.
        """
        try:
            file_hash = self._calculate_md5(text)

            # Verificação de cache por hash MD5
            if file_hash and hasattr(self.db, "check_hash"):
                if self.db.check_hash(file_hash, project_id):
                    self.update_state(stats_inc={"cached": 1})
                    return "Cache Hit"

            logger.info(f"Indexando: {source} (Projeto: {project_id})")
            self.update_state(
                current_file=os.path.basename(source),
                current_folder=os.path.dirname(source),
                project_id=project_id
            )

            splitter = self._get_splitter(file_path or source)
            chunks = splitter.split_text(text)
            total = len(chunks)
            logger.info(f"Dividido em {total} fragmentos ({os.path.splitext(source or '')[1] or 'texto'}).")

            for i, chunk in enumerate(chunks):
                is_last = i == total - 1
                should_unload = (not session_active) and is_last

                metadata = {
                    "source": source,
                    "project_id": project_id,
                    "chunk_index": i,
                    "total_chunks": total,
                    "category": self._get_category(source),
                    "tags": self._get_tags(source)
                }

                # Heartbeat para arquivos grandes
                if total > 10 and (i % 5 == 0 or is_last):
                    logger.info(f"  > Progresso {source}: Fragmento {i+1}/{total}...")

                try:
                    # Tentativa normal de gerar embedding
                    embedding = self.ollama.get_embedding(chunk, auto_unload=should_unload)
                except Exception as e:
                    logger.warning(f"  ! Falha no fragmento {i+1}/{total} de {source}. Tentando subdividir... Erro: {str(e)}")
                    try:
                        # Subdivide o fragmento problemático em 4 pedaços menores
                        sub_size = len(chunk) // 4
                        sub_chunks = [chunk[j:j+sub_size] for j in range(0, len(chunk), sub_size)]
                        
                        for sc_idx, sub_chunk in enumerate(sub_chunks):
                            if not sub_chunk.strip(): continue
                            # Embedding para o sub-pedaço
                            sub_emb = self.ollama.get_embedding(sub_chunk, auto_unload=should_unload and sc_idx == len(sub_chunks)-1)
                            sub_id = f"{str(uuid.uuid4())}_sub_{sc_idx}"
                            
                            logger.debug(f"  [DB] Gravando sub-fragmento {sc_idx}...")
                            self.db.add_document(sub_id, sub_emb, sub_chunk, {**metadata, "sub_chunk": sc_idx}, file_hash=file_hash)
                            logger.debug(f"  [DB] Sub-fragmento {sc_idx} OK.")
                        
                        logger.info(f"  ✓ Fragmento {i+1} recuperado via subdivisão.")
                        continue # Pula para o próximo fragmento principal
                    except Exception as sub_e:
                        logger.error(f"  ✗ Falha crítica no fragmento {i+1} mesmo após subdivisão: {str(sub_e)}")
                        self.update_state(stats_inc={"errors": 1})
                        continue

                # Inserção normal se o embedding funcionou
                doc_id = str(uuid.uuid4())
                logger.debug(f"  [DB] Gravando fragmento {i+1}/{total}...")
                self.db.add_document(doc_id, embedding, chunk, metadata, file_hash=file_hash)
                logger.debug(f"  [DB] Fragmento {i+1}/{total} OK.")

            self.update_state(
                stats_inc={"new": 1},
                current_file="" # Limpa ao terminar o arquivo
            )
            return f"{total} fragmentos indexados com sucesso."

        except Exception as e:
            logger.error(f"Erro ao indexar texto de {source}: {str(e)}")
            self.update_state(stats_inc={"errors": 1})
            raise

    def index_file_by_path(self, file_path: str, project_id: str, session_active: bool = False) -> str:
        """Lê o arquivo, calcula MD5 e indexa se o conteúdo mudou desde a última indexação."""
        try:
            if not os.path.exists(file_path):
                return f"Erro: Arquivo {file_path} não encontrado."

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

            if not text.strip():
                return "Arquivo vazio."

            return self.index_text(text, file_path, project_id, file_path=file_path, session_active=session_active)
        except Exception as e:
            logger.error(f"Erro ao ler/indexar arquivo {file_path}: {str(e)}")
            self.update_state(stats_inc={"errors": 1})
            return f"Erro: {str(e)}"

    def search_and_generate(self, question: str, project_id: str = None) -> dict:
        """Realiza busca vetorial e gera resposta RAG."""
        try:
            # 1. Gera embedding da pergunta
            question_embedding = self.ollama.get_embedding(question, auto_unload=False)

            # 2. Busca no banco
            results = self.db.search(question_embedding, project_id=project_id, n_results=5)

            if not results:
                return {"answer": "Nenhum contexto encontrado.", "sources": []}

            # 3. Monta contexto para o modelo
            context_texts = []
            sources = []
            for doc in results:
                context_texts.append(doc["content"])
                sources.append(doc["metadata"])

            context_str = "\n\n".join(context_texts)

            # 4. Gera resposta
            answer = self.ollama.generate_response(question, context_str, project_id=project_id)

            return {"answer": answer, "sources": sources}
        except Exception as e:
            logger.error(f"Erro no fluxo RAG: {str(e)}")
            return {"answer": f"Erro: {str(e)}", "sources": []}

    def list_indexed_sources(self, project_id: str = None) -> List[Dict[str, Any]]:
        """Lista todas as fontes únicas indexadas."""
        return self.db.list_sources(project_id)

    def clear_database(self, project_id: str = None) -> str:
        """Limpa a base de dados (projeto específico ou global)."""
        if project_id:
            return self.db.delete_by_project(project_id)
        else:
            return self.db.clear()
