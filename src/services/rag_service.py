import os
import uuid
import hashlib
import json
import datetime
import re
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
        
        # Callback opcional disparado para emitir logs no terminal de eventos
        self.log_callback = None

        # Configuração de chunking
        settings = self.config.get_all().get("indexing", {})
        self.chunk_size = settings.get("chunk_size", int(os.getenv("CHUNK_SIZE", "8000")))
        self.chunk_overlap = settings.get("chunk_overlap", int(os.getenv("CHUNK_OVERLAP", "1000")))
        # Configuração de busca RAG
        rag_settings = self.config.get_all().get("rag", {})
        self.distance_threshold = rag_settings.get("distance_threshold", 0.75)
        self.n_results = rag_settings.get("n_results", 5)
        # Diretórios de Cache e Histórico
        self.history_dir = os.path.join("logs", "rag_history")
        self.index_file = os.path.join(self.history_dir, "index.json")
        os.makedirs(self.history_dir, exist_ok=True)
        
        logger.info(f"RAGService inicializado | Store: {self.store_type.upper()} | Chunk: {self.chunk_size} chars / Overlap: {self.chunk_overlap} chars")
        self._persist_state()

    def _normalize_question(self, question: str) -> str:
        """Normaliza a pergunta para uso como chave no cache."""
        q = question.lower().strip()
        q = re.sub(r'[^\w\s]', '', q)
        q = re.sub(r'\s+', ' ', q)
        return q

    def _get_cache_index(self) -> dict:
        """Carrega o índice mestre de cache."""
        if not os.path.exists(self.index_file):
            return {}
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao ler cache index: {e}")
            return {}

    def _save_cache_index(self, index_data: dict):
        """Salva o índice mestre de cache."""
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao salvar cache index: {e}")

    def _check_cache(self, question: str, project_id: str = None) -> dict:
        """Verifica se a pergunta já foi respondida recentemente."""
        folder = project_id if project_id else "global"
        norm_q = self._normalize_question(question)
        if not norm_q: return None
        
        index_data = self._get_cache_index()
        if folder in index_data and norm_q in index_data[folder]:
            cache_entry = index_data[folder][norm_q]
            file_path = cache_entry.get("file_path")
            
            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        
                    # Extrai a resposta usando regex ou split
                    answer_match = re.search(r"## 🤖 Resposta Gerada\s+(.*?)\s+## 📚 Fontes e Contexto", content, re.DOTALL)
                    if answer_match:
                        logger.info(f"⚡ [CACHE HIT] Resposta recuperada instantaneamente para: {norm_q}")
                        return {
                            "answer": answer_match.group(1).strip() + "\n\n*(Resposta instantânea carregada do cache local)*",
                            "sources": [{"info": f"Veja o log completo em {file_path}"}],
                            "project_id": project_id,
                            "cached": True
                        }
                except Exception as e:
                    logger.error(f"Erro ao ler arquivo de cache {file_path}: {e}")
        return None

    def _log_and_cache(self, question: str, answer: str, sources: list, project_id: str = None):
        """Salva a consulta em um arquivo Markdown e atualiza o index.json."""
        try:
            folder = project_id if project_id else "global"
            target_dir = os.path.join(self.history_dir, folder)
            os.makedirs(target_dir, exist_ok=True)
            
            timestamp = datetime.datetime.now()
            ts_str = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
            ts_display = timestamp.strftime("%d/%m/%Y %H:%M:%S")
            
            file_name = f"query_{ts_str}.md"
            file_path = os.path.join(target_dir, file_name)
            
            # Monta o Markdown
            md_lines = [
                f"# Consulta RAG: {folder} ({ts_display})",
                "",
                "## ❓ Pergunta",
                f"> {question}",
                "",
                "## 🤖 Resposta Gerada",
                answer,
                "",
                "## 📚 Fontes e Contexto Utilizados",
                "| Arquivo Fonte | Categoria | Chunk / Total | Tags |",
                "|---|---|---|---|"
            ]
            
            for s in sources:
                if isinstance(s, dict):
                    source_path = s.get("source", "N/A")
                    category = s.get("category", "N/A")
                    chunk_idx = s.get("chunk_index", 0)
                    total_chunks = s.get("total_chunks", 0)
                    tags = ", ".join(s.get("tags", []))
                    md_lines.append(f"| `{source_path}` | {category} | {chunk_idx} / {total_chunks} | [{tags}] |")
                else:
                    md_lines.append(f"| {str(s)} | | | |")
                    
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(md_lines))
                
            # Atualiza Cache Index
            norm_q = self._normalize_question(question)
            if norm_q:
                index_data = self._get_cache_index()
                if folder not in index_data:
                    index_data[folder] = {}
                index_data[folder][norm_q] = {
                    "file_path": file_path.replace("\\", "/"),
                    "timestamp": ts_display,
                    "question_raw": question
                }
                self._save_cache_index(index_data)
                
        except Exception as e:
            logger.error(f"Erro ao salvar log/cache do RAG: {e}")

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
                    self.update_state(
                        current_file=os.path.basename(source),
                        current_folder=os.path.dirname(source),
                        project_id=project_id,
                        stats_inc={"cached": 1}
                    )
                    if self.log_callback:
                        self.log_callback(f"  > [CACHE HIT] {os.path.basename(source)}")
                    return "Cache Hit"

            # Se chegou aqui, ou é arquivo novo ou o conteúdo mudou.
            # Limpa qualquer versão anterior do arquivo no banco (Edição / Sincronização)
            if hasattr(self.db, "delete_by_source"):
                deleted = self.db.delete_by_source(source, project_id)
                if deleted > 0:
                    logger.debug(f"Arquivo modificado: {deleted} fragmentos antigos removidos de {source}.")


            logger.info(f"Indexando: {source} (Projeto: {project_id})")
            if self.log_callback:
                self.log_callback(f"Indexando: {os.path.basename(source)}")
            self.update_state(
                current_file=os.path.basename(source),
                current_folder=os.path.dirname(source),
                project_id=project_id
            )

            splitter = self._get_splitter(file_path or source)
            chunks = splitter.split_text(text)
            total = len(chunks)
            logger.info(f"Dividido em {total} fragmentos ({os.path.splitext(source or '')[1] or 'texto'}).")
            if self.log_callback:
                self.log_callback(f"  > Dividido em {total} fragmento(s).")

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
                
                if self.log_callback:
                    if total <= 10 or (i % 5 == 0 or is_last):
                        self.log_callback(f"  [FRAG] Processando fragmento {i+1}/{total}...")

                try:
                    # Tentativa normal de gerar embedding
                    embedding = self.ollama.get_embedding(chunk, auto_unload=should_unload)
                except Exception as e:
                    logger.warning(f"  ! Falha no fragmento {i+1}/{total} de {source}. Tentando subdividir... Erro: {str(e)}")
                    if self.log_callback:
                        self.log_callback(f"  ! Falha no fragmento {i+1}/{total}. Tentando subdividir...")
                    try:
                        # Subdivide o fragmento problemático em 4 pedaços menores
                        sub_size = len(chunk) // 4
                        sub_chunks = [chunk[j:j+sub_size] for j in range(0, len(chunk), sub_size)]
                        
                        for sc_idx, sub_chunk in enumerate(sub_chunks):
                            if not sub_chunk.strip(): continue
                            # Embedding para o sub-pedaço
                            sub_emb = self.ollama.get_embedding(sub_chunk, auto_unload=should_unload and sc_idx == len(sub_chunks)-1)
                            sub_id = str(uuid.uuid4())
                            
                            logger.debug(f"  [DB] Gravando sub-fragmento {sc_idx}...")
                            self.db.add_document(sub_id, sub_emb, sub_chunk, {**metadata, "sub_chunk": sc_idx}, file_hash=file_hash)
                            logger.debug(f"  [DB] Sub-fragmento {sc_idx} OK.")
                        
                        logger.info(f"  ✓ Fragmento {i+1} recuperado via subdivisão.")
                        if self.log_callback:
                            self.log_callback(f"  ✓ Fragmento {i+1} recuperado via subdivisão.")
                        continue # Pula para o próximo fragmento principal
                    except Exception as sub_e:
                        logger.error(f"  ✗ Falha crítica no fragmento {i+1} mesmo após subdivisão: {str(sub_e)}")
                        if self.log_callback:
                            self.log_callback(f"  ✗ Falha crítica no fragmento {i+1} após subdivisão.")
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
                if self.log_callback:
                    self.log_callback(f"Erro: Arquivo {os.path.basename(file_path)} não encontrado.")
                return f"Erro: Arquivo {file_path} não encontrado."

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

            if not text.strip():
                if self.log_callback:
                    self.log_callback(f"Pulado: {os.path.basename(file_path)} está vazio.")
                return "Arquivo vazio."

            return self.index_text(text, file_path, project_id, file_path=file_path, session_active=session_active)
        except Exception as e:
            logger.error(f"Erro ao ler/indexar arquivo {file_path}: {str(e)}")
            if self.log_callback:
                self.log_callback(f"Erro ao ler/indexar arquivo {os.path.basename(file_path)}: {str(e)}")
            self.update_state(stats_inc={"errors": 1})
            raise

    def cleanup_deleted_files(self, project_id: str, current_files_on_disk: list[str]) -> int:
        """Compara os arquivos no banco com os arquivos reais no disco e deleta os fantasmas."""
        if not hasattr(self.db, "list_sources") or not hasattr(self.db, "delete_by_source"):
            return 0
            
        try:
            logger.info(f"Iniciando Garbage Collection para o projeto {project_id}...")
            if self.log_callback:
                self.log_callback(f"Iniciando Sincronização/Limpeza (Garbage Collection)...")
                
            indexed_sources = self.db.list_sources(project_id)
            # Normalizar os caminhos para facilitar comparação
            disk_paths = {os.path.normpath(os.path.abspath(f)) for f in current_files_on_disk}
            
            deleted_count = 0
            for item in indexed_sources:
                source = item.get("source")
                if not source:
                    continue
                norm_source = os.path.normpath(os.path.abspath(source))
                
                # Se a fonte que está no banco NÃO existe mais na lista de arquivos escaneados
                if norm_source not in disk_paths:
                    logger.info(f"Garbage Collection: Removendo arquivo fantasma do banco: {source}")
                    if self.log_callback:
                        self.log_callback(f"  > [GC DELETED] Removendo arquivo excluído/movido: {os.path.basename(source)}")
                    self.db.delete_by_source(source, project_id)
                    deleted_count += 1
                    
            if deleted_count > 0:
                logger.info(f"Garbage Collection: {deleted_count} arquivos fantasmas removidos do projeto {project_id}.")
                if self.log_callback:
                    self.log_callback(f"Sincronização concluída: {deleted_count} arquivos fantasmas limpos do banco.")
                    
            return deleted_count
        except Exception as e:
            logger.error(f"Erro no Garbage Collection do RAG: {str(e)}")
            return 0


    def search_and_generate(self, question: str, project_id: str = None) -> dict:
        """Realiza busca vetorial e gera resposta RAG."""
        try:
            # 0. Verifica o Cache Instantâneo
            cached = self._check_cache(question, project_id)
            if cached:
                return cached

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

            # 5. Salva o Log e atualiza o Cache
            self._log_and_cache(question, answer, sources, project_id)

            return {"answer": answer, "sources": sources}
        except Exception as e:
            logger.error(f"Erro no fluxo RAG: {str(e)}")
            return {"answer": f"Erro: {str(e)}", "sources": []}

    def search_project_isolated(self, question: str, project_id: str) -> dict:
        """Busca isolada em um único projeto. Rápida e precisa.
        Uso: quando o projeto é conhecido. Gera embedding e busca apenas naquela tabela.
        """
        try:
            cached = self._check_cache(question, project_id)
            if cached:
                return cached

            logger.info(f"Busca isolada | Projeto: {project_id} | Pergunta: {question[:80]}")
            question_embedding = self.ollama.get_embedding(question, auto_unload=False)
            results = self.db.search(question_embedding, project_id=project_id, n_results=5)
            if not results:
                return {"answer": "Nenhum contexto encontrado neste projeto.", "sources": [], "project_id": project_id}
            context_str = "\n\n".join(r["content"] for r in results)
            answer = self.ollama.generate_response(question, context_str, project_id=project_id)
            
            sources = [r["metadata"] for r in results]
            self._log_and_cache(question, answer, sources, project_id)
            
            return {"answer": answer, "sources": sources, "project_id": project_id}
        except Exception as e:
            logger.error(f"Erro na busca isolada [{project_id}]: {str(e)}")
            return {"answer": f"Erro: {str(e)}", "sources": [], "project_id": project_id}

    def search_all_projects_sequential(self, question: str) -> dict:
        """Busca em todos os projetos sequencialmente.
        ⚠️ Lenta: percorre todas as tabelas rag_* uma a uma.
        Uso: quando não se sabe em qual projeto está a informação.
        """
        try:
            cached = self._check_cache(question, "global")
            if cached:
                return cached
                

            logger.info(f"Busca global (todos projetos) | Pergunta: {question[:80]}")
            question_embedding = self.ollama.get_embedding(question, auto_unload=False)
            all_tables = self.db._get_all_tables()
            results_by_project = {}
            for table in all_tables:
                project_name = table[4:]  # remove prefixo "rag_"
                results = self.db.search(question_embedding, project_id=project_name, n_results=3)
                if results:
                    results_by_project[project_name] = results

            if not results_by_project:
                return {"answer": "Nenhum contexto encontrado em nenhum projeto.", "sources": [], "projects_searched": all_tables}

            # Combina todos os resultados para gerar uma resposta unificada
            context_parts = []
            all_sources = []
            for proj, docs in results_by_project.items():
                context_parts.append(f"[Projeto: {proj}]")
                for d in docs:
                    context_parts.append(d["content"])
                    all_sources.append(d["metadata"])

            context_str = "\n\n".join(context_parts)
            answer = self.ollama.generate_response(question, context_str)
            
            self._log_and_cache(question, answer, all_sources, "global")
            
            return {"answer": answer, "sources": all_sources, "projects_searched": list(results_by_project.keys())}
        except Exception as e:
            logger.error(f"Erro na busca global: {str(e)}")
            return {"answer": f"Erro: {str(e)}", "sources": [], "projects_searched": []}

    def cross_project_analysis(self, searches: list, analysis_prompt: str) -> dict:
        """Busca sequencial em múltiplos projetos e análise cruzada dos resultados.

        Args:
            searches: Lista de {"project_id": str, "query": str}
            analysis_prompt: O que analisar com os dados coletados de todos os projetos.

        Processa uma busca de cada vez (fila síncrona) para não sobrecarregar o Ollama,
        depois combina tudo e gera análise unificada.
        """
        try:
            logger.info(f"Análise cruzada | {len(searches)} projeto(s) | Prompt: {analysis_prompt[:80]}")
            collected = {}

            # Fila sequencial: um embedding por vez
            for search in searches:
                project_id = search.get("project_id", "")
                query = search.get("query", "")
                if not project_id or not query:
                    logger.warning(f"Busca inválida ignorada: {search}")
                    continue
                logger.info(f"  > Buscando em '{project_id}': {query[:60]}")
                embedding = self.ollama.get_embedding(query, auto_unload=False)
                results = self.db.search(embedding, project_id=project_id, n_results=5)
                collected[project_id] = {"query": query, "results": results}

            if not collected:
                return {"analysis": "Nenhum resultado coletado.", "raw_results": {}, "searches": searches}

            # Monta contexto combinado para análise
            context_parts = []
            for project_id, data in collected.items():
                context_parts.append(f"=== Projeto: {project_id} | Busca: '{data['query']}' ===")
                if data["results"]:
                    for r in data["results"]:
                        context_parts.append(r["content"])
                else:
                    context_parts.append("(Nenhum fragmento encontrado para esta busca)")
                context_parts.append("")

            context_str = "\n\n".join(context_parts)
            logger.info(f"Gerando análise cruzada com {len(collected)} projeto(s)...")
            analysis = self.ollama.generate_response(analysis_prompt, context_str)

            return {
                "analysis": analysis,
                "raw_results": {p: {"query": d["query"], "fragments_found": len(d["results"])} for p, d in collected.items()},
                "searches": searches
            }
        except Exception as e:
            logger.error(f"Erro na análise cruzada: {str(e)}")
            return {"analysis": f"Erro: {str(e)}", "raw_results": {}, "searches": searches}

    # ══════════════════════════════════════════════════════════════════════
    # MODO RAW — busca sem geração de resposta pelo modelo local
    # ══════════════════════════════════════════════════════════════════════

    def _merge_overlapping_texts(self, text1: str, text2: str) -> str:
        """Mescla dois textos que possuem sobreposição na junção (overlap)."""
        min_len = min(len(text1), len(text2))
        # Procura sobreposição na junção de até 2000 caracteres (nosso overlap padrão é 1000)
        for i in range(min(min_len, 2000), 0, -1):
            if text1.endswith(text2[:i]):
                return text1 + text2[i:]
        return text1 + "\n\n... [continuação] ...\n\n" + text2

    def search_raw(self, question: str, project_id: str = None, n_results: int = None, threshold: float = None, custom_filename: str = None) -> dict:
        """Busca vetorial que retorna fragmentos brutos SEM passar pelo modelo de geração.

        O modelo chamador (Claude, Gemini, etc.) interpreta os resultados diretamente.
        Usa apenas o modelo de embedding para gerar o vetor da pergunta.

        Args:
            question: Pergunta para busca semântica.
            project_id: Filtra por projeto. None = todos.
            n_results: Quantidade de resultados a buscar (antes do filtro de distância).
            threshold: Distância máxima aceitável. Resultados acima são descartados.

        Returns:
            dict com: fragments (lista de hits), discarded (lista dos descartados),
            threshold usado, project_id, cached (bool).
        """
        try:
            # Cache instantâneo
            cached = self._check_raw_cache(question, project_id)
            if cached:
                return cached

            # Defaults do config
            if n_results is None:
                n_results = self.n_results
            if threshold is None:
                threshold = self.distance_threshold

            logger.info(f"Busca RAW | Projeto: {project_id or 'global'} | Threshold: {threshold} | Pergunta: {question[:80]}")

            # Embedding da pergunta (descarrega após uso — não precisa do modelo de chat)
            question_embedding = self.ollama.get_embedding(question, auto_unload=True)

            # Busca vetorial
            if project_id:
                results = self.db.search(question_embedding, project_id=project_id, n_results=n_results)
            else:
                results = self.db.search(question_embedding, project_id=None, n_results=n_results)

            if not results:
                return {
                    "fragments": [],
                    "discarded": [],
                    "threshold": threshold,
                    "project_id": project_id,
                    "cached": False
                }

            # 1. Pré-processamento e Penalização Cossena para Locales / Traduções
            translation_keywords = {"traduzir", "tradução", "traducao", "idioma", "locale", "lang", "translation", "dicionário", "dicionario"}
            is_translation_query = any(kw in question.lower() for kw in translation_keywords)

            processed_results = []
            for doc in results:
                meta = doc.get("metadata", {})
                source_path = meta.get("source", "").lower().replace("\\", "/")
                dist = doc["distance"]

                is_locale_file = "/locales/" in source_path or "/langs/" in source_path or "es.lua" in source_path or "pt.lua" in source_path or "pl.lua" in source_path
                if is_locale_file and not is_translation_query:
                    dist = dist * 1.5
                    logger.info(f" Penalização cossena aplicada ao arquivo de locale: {os.path.basename(source_path)} (distância de {doc['distance']:.4f} -> {dist:.4f})")

                processed_results.append({
                    "content": doc["content"],
                    "metadata": doc["metadata"],
                    "distance": dist
                })

            # 2. Filtragem pelo threshold de distância
            filtered_entries = []
            discarded = []
            for entry in processed_results:
                if entry["distance"] <= threshold:
                    filtered_entries.append(entry)
                else:
                    discarded.append(entry)

            # 2.1 Deduplicação de Conteúdo Exato
            seen_contents = set()
            unique_filtered_entries = []
            for entry in filtered_entries:
                # Normaliza espaçamento para comparação precisa e limpa
                norm_content = " ".join(entry["content"].split())
                if norm_content not in seen_contents:
                    seen_contents.add(norm_content)
                    unique_filtered_entries.append(entry)
                else:
                    logger.info(f" Chunk duplicado ignorado para o arquivo: {os.path.basename(entry['metadata'].get('source', ''))}")
            
            filtered_entries = unique_filtered_entries

            # 3. Agrupamento e Fusão de Chunks Adjacentes (De-overlapping)
            fragments = []
            if filtered_entries:
                by_source = {}
                for entry in filtered_entries:
                    src = entry["metadata"].get("source", "unknown")
                    if src not in by_source:
                        by_source[src] = []
                    by_source[src].append(entry)

                for src, entries in by_source.items():
                    # Ordena pelo índice sequencial original do chunk
                    entries.sort(key=lambda x: x["metadata"].get("chunk_index", 0))

                    merged_entries = []
                    current = entries[0]

                    for next_entry in entries[1:]:
                        curr_idx = current["metadata"].get("chunk_index", 0)
                        next_idx = next_entry["metadata"].get("chunk_index", 0)

                        # Se os chunks forem sequenciais (contíguos)
                        if next_idx == curr_idx + 1:
                            logger.info(f" Mesclando chunks adjacentes {curr_idx} e {next_idx} do arquivo: {os.path.basename(src)}")
                            merged_content = self._merge_overlapping_texts(current["content"], next_entry["content"])
                            min_dist = min(current["distance"], next_entry["distance"])
                            current = {
                                "content": merged_content,
                                "metadata": current["metadata"].copy(),
                                "distance": min_dist
                            }
                            current["metadata"]["chunk_index"] = next_idx  # Atualiza index para permitir fusões consecutivas múltiplas
                        else:
                            merged_entries.append(current)
                            current = next_entry

                    merged_entries.append(current)
                    fragments.extend(merged_entries)

                # Reordena a lista final de blocos pela menor distância cossena
                fragments.sort(key=lambda x: x["distance"])

            # Salva log e cache
            self._log_raw_results(question, fragments, discarded, threshold, project_id, custom_filename=custom_filename)

            return {
                "fragments": fragments,
                "discarded": discarded,
                "threshold": threshold,
                "project_id": project_id,
                "cached": False
            }
        except Exception as e:
            logger.error(f"Erro na busca raw [{project_id or 'global'}]: {str(e)}")
            return {
                "fragments": [],
                "discarded": [],
                "threshold": threshold or self.distance_threshold,
                "project_id": project_id,
                "cached": False,
                "error": str(e)
            }

    def _check_raw_cache(self, question: str, project_id: str = None) -> dict:
        """Verifica cache para busca raw — retorna o resultado salvo se existir."""
        folder = project_id if project_id else "global"
        norm_q = self._normalize_question(question)
        if not norm_q:
            return None

        index_data = self._get_cache_index()
        if folder in index_data and norm_q in index_data[folder]:
            cache_entry = index_data[folder][norm_q]
            file_path = cache_entry.get("file_path")

            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    logger.info(f"⚡ [CACHE HIT RAW] Resultado recuperado: {norm_q}")
                    return {
                        "fragments": [],
                        "discarded": [],
                        "threshold": self.distance_threshold,
                        "project_id": project_id,
                        "cached": True,
                        "cached_file": file_path,
                        "cached_content": content
                    }
                except Exception as e:
                    logger.error(f"Erro ao ler cache raw {file_path}: {e}")
        return None

    def _log_raw_results(self, question: str, fragments: list, discarded: list, threshold: float, project_id: str = None, custom_filename: str = None):
        """Salva os resultados brutos da busca vetorial em Markdown e atualiza o index.json."""
        try:
            folder = project_id if project_id else "global"
            target_dir = os.path.join(self.history_dir, folder)
            os.makedirs(target_dir, exist_ok=True)

            timestamp = datetime.datetime.now()
            ts_display = timestamp.strftime("%d/%m/%Y %H:%M:%S")

            if custom_filename:
                file_name = custom_filename
            else:
                ts_str = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
                file_name = f"query_{ts_str}.md"

            file_path = os.path.join(target_dir, file_name)

            md_lines = [
                f"# Busca RAG: {folder} ({ts_display})",
                "",
                "## ❓ Pergunta",
                f"> {question}",
                "",
                f"## 📊 Resultados ({len(fragments)} fragmentos | threshold: {threshold} | descartados: {len(discarded)})",
                ""
            ]

            for i, frag in enumerate(fragments, 1):
                meta = frag.get("metadata", {})
                source = meta.get("source", "desconhecido")
                basename = os.path.basename(source)
                category = meta.get("category", "N/A")
                tags = meta.get("tags", [])
                distance = frag.get("distance", 0)

                md_lines.extend([
                    f"### [{i}] {basename} — distância: {distance:.4f}",
                    f"- **Fonte**: `{source}`",
                    f"- **Categoria**: {category} | **Tags**: [{', '.join(tags)}]",
                    "",
                    "```",
                    frag.get("content", "").strip(),
                    "```",
                    ""
                ])

            if discarded:
                md_lines.extend([
                    f"## ❌ Descartados (distância > {threshold})",
                    "| Fonte | Distância |",
                    "|---|---|"
                ])
                for d in discarded:
                    d_meta = d.get("metadata", {})
                    d_source = os.path.basename(d_meta.get("source", "?"))
                    d_dist = d.get("distance", 0)
                    md_lines.append(f"| `{d_source}` | {d_dist:.4f} |")
                md_lines.append("")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(md_lines))

            # Atualiza Cache Index
            norm_q = self._normalize_question(question)
            if norm_q:
                index_data = self._get_cache_index()
                if folder not in index_data:
                    index_data[folder] = {}
                index_data[folder][norm_q] = {
                    "file_path": file_path.replace("\\", "/"),
                    "timestamp": ts_display,
                    "question_raw": question,
                    "mode": "raw",
                    "fragments_count": len(fragments),
                    "discarded_count": len(discarded)
                }
                self._save_cache_index(index_data)

            logger.info(f"Resultado raw salvo em: {file_path}")

        except Exception as e:
            logger.error(f"Erro ao salvar log raw do RAG: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # Utilitários
    # ══════════════════════════════════════════════════════════════════════

    def index_image(self, file_path: str, project_id: str) -> str:
        """Processa uma imagem com Vision, extrai descrição e indexa no vetor."""
        try:
            if not os.path.exists(file_path):
                if self.log_callback:
                    self.log_callback(f"Erro: Imagem {os.path.basename(file_path)} não encontrada.")
                return f"Erro: Imagem {file_path} não encontrada."

            logger.info(f"Indexando Imagem via Vision: {file_path} (Projeto: {project_id})")
            if self.log_callback:
                self.log_callback(f"Indexando Imagem (Vision): {os.path.basename(file_path)}")
            self.update_state(
                current_file=os.path.basename(file_path),
                current_folder=os.path.dirname(file_path),
                project_id=project_id
            )

            # Extrai descrição via Ollama Vision
            description = self.ollama.describe_image(file_path)

            if not description or not description.strip():
                self.update_state(stats_inc={"errors": 1})
                if self.log_callback:
                    self.log_callback(f"  ✗ Falha ao gerar descrição Vision para {os.path.basename(file_path)}")
                return "Falha ao gerar descrição da imagem ou descrição vazia."

            # O contexto da imagem é a descrição textutal dela.
            context = f"Arquivo de Imagem: {os.path.basename(file_path)}\n\nDescrição Vision:\n{description}"
            
            # Adiciona metadados extra no texto para a indexação
            return self.index_text(context, file_path, project_id, file_path=file_path)
            
        except Exception as e:
            logger.error(f"Erro ao indexar imagem {file_path}: {str(e)}")
            self.update_state(stats_inc={"errors": 1})
            raise

    def list_indexed_sources(self, project_id: str = None) -> List[Dict[str, Any]]:
        """Lista todas as fontes únicas indexadas."""
    def list_indexed_sources(self, project_id=None):
        """Lista todas as fontes unicas indexadas."""
        return self.db.list_sources(project_id)

    def clear_database(self, project_id=None):
        """Limpa a base de dados (projeto especifico ou global)."""
        if project_id:
            return self.db.delete_by_project(project_id)
        else:
            return self.db.clear()
