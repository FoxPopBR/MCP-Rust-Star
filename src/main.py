"""
MCP Rust Star Knowledge Server
Servidor de base de conhecimento RAG local para os projetos Rust Star, FoxOT e FoxClient.

Ferramentas disponíveis:
  Gestão de Projetos : register_project, list_projects
  Indexação          : index_file, index_directory, index_image,
                       batch_index_projects, scan_extensions,
                       get_embed_status, cancel_embed,
                       retry_failed_files
  Busca RAG          : ask_knowledge_base
  Análise Visual     : analyze_screenshot
  Fontes Indexadas   : list_indexed_sources
  Sistema            : get_server_settings, update_indexing_settings,
                       update_vision_settings, reset_server_settings,
                       check_ollama_status, get_gpu_status, unload_vram,
                       clear_knowledge_base
"""

import asyncio
import datetime
import os
import sys
import json
import time
from collections import Counter
from functools import wraps
import threading

from mcp.server.fastmcp import FastMCP
from src.services.rag_service import RAGService
from src.services.telemetry_writer import TelemetryWriter, InventoryProvider
from src.services.event_bus import get_event_bus
from src.services.model_guard import with_model_guard, get_model_guard
from src.services.observability import register_observability_routes
from tools.logger import logger

# ─── Inicialização do servidor ─────────────────────────────────────────────────

os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)

_defaults_path = os.path.join("data", "defaults.json")
_defaults: dict = {}
if os.path.exists(_defaults_path):
    with open(_defaults_path, encoding="utf-8") as _f:
        _defaults = json.load(_f)

_srv = _defaults.get("server", {})
_HOST = _srv.get("host", "127.0.0.1")
_PORT = int(_srv.get("port", 8765))
_TRANSPORT = _srv.get("transport", "streamable-http")

_SERVER_START_TIME = time.time()

mcp = FastMCP("Rust Star Knowledge Server", host=_HOST, port=_PORT)
rag = RAGService()

PROJECTS_FILE = "data/projects.json"
BATCH_PROGRESS_FILE = "data/batch_progress.json"

_bus = get_event_bus()
_inventory = InventoryProvider(rag.db)
_batch_progress_cache: dict = {}
_server_extra: dict = {"last_query": None}
_telemetry = TelemetryWriter(
    inventory=_inventory,
    bus=_bus,
    get_embed_state_fn=lambda: _embed_state,
    get_rag_state_fn=lambda: rag.state,
    get_batch_progress_fn=lambda: _batch_progress_cache,
    get_server_extra_fn=lambda: _server_extra,
)

rag._on_state_change = lambda: _bus.emit("rag.state.changed", {})

register_observability_routes(mcp, rag, _bus, _SERVER_START_TIME)


# ─── Helpers de projetos ───────────────────────────────────────────────────────

def load_projects() -> dict:
    if os.path.exists(PROJECTS_FILE):
        try:
            with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao carregar projetos: {str(e)}")
    return {}


def save_project(project_id: str, path: str) -> None:
    projects = load_projects()
    projects[project_id] = path
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(projects, f, indent=4, ensure_ascii=False)


def load_batch_progress() -> dict:
    """Carrega progresso de uma sessão batch anterior."""
    if os.path.exists(BATCH_PROGRESS_FILE):
        try:
            with open(BATCH_PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_batch_progress(progress: dict) -> None:
    """Persiste o progresso atual da sessão batch e replica no snapshot do dashboard."""
    try:
        with open(BATCH_PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Falha ao salvar progresso batch: {e}")

    # Atualiza cache em memória e dispara publicação de telemetria.
    try:
        _batch_progress_cache.clear()
        _batch_progress_cache.update(progress or {})
    except Exception:
        pass
    try:
        _inventory.invalidate()
    except Exception:
        pass
    _bus.emit("embed.batch.progress", {})


def get_project_for_path(file_path: str) -> str | None:
    """Identifica o project_id pelo caminho do arquivo (longest-match primeiro)."""
    projects = load_projects()
    file_norm = os.path.normpath(os.path.abspath(file_path)).lower()
    for project_id, project_root in sorted(projects.items(), key=lambda x: len(x[1]), reverse=True):
        root_norm = os.path.normpath(os.path.abspath(project_root)).lower()
        if file_norm == root_norm or file_norm.startswith(root_norm + os.sep):
            return project_id
    return None


# ─── Decorator de logging para ferramentas MCP ────────────────────────────────

def mcp_tool_with_logging(func):
    """Registra a função como ferramenta MCP com logging, telemetria e eventos."""
    @mcp.tool()
    @wraps(func)
    async def wrapper(*args, **kwargs):
        tool_name = func.__name__
        logger.info(f"[TOOL START] Executando '{tool_name}'...")
        start_time = datetime.datetime.now()
        _bus.emit("tool.invoked", {"tool": tool_name})
        with _telemetry.activity():
            try:
                result = await func(*args, **kwargs)
                duration = (datetime.datetime.now() - start_time).total_seconds()
                logger.info(f"[TOOL END] '{tool_name}' concluída em {duration:.2f}s")
                _bus.emit("tool.completed", {"tool": tool_name, "duration_s": round(duration, 2)})
                return result
            except Exception as e:
                duration = (datetime.datetime.now() - start_time).total_seconds()
                logger.error(f"[TOOL ERROR] Falha em '{tool_name}' após {duration:.2f}s")
                logger.error_with_traceback(e, tool_name)
                _telemetry.set_activity_error(True)
                _bus.emit("tool.failed", {"tool": tool_name, "error": str(e)[:200]})
                return f"Erro na ferramenta '{tool_name}': {str(e)}"
    return wrapper


# ═══════════════════════════════════════════════════════════════════════════════
# ESTADO GLOBAL DO EMBED EM BACKGROUND
# ═══════════════════════════════════════════════════════════════════════════════

_embed_task: asyncio.Task | None = None

_embed_state: dict = {
    "running": False,
    "canceled": False,
    "current_project": None,
    "current_file": None,
    "current_folder": None,
    "total_expected": 0,
    "stats": {"new": 0, "cached": 0, "skipped": 0, "errors": 0},
    "stats_by_ext": {},       # {"ext": count} for embedded files
    "error_files": [],        # [{"file": path, "error": str, "project_id": str}]
    "queue": [],              # [{"project_id": str, "project_root": str, "force": bool}]
    "completed": [],          # project_ids concluídos nesta sessão
    "log_lines": [],          # buffer circular de log (últimas MAX_LOG_LINES entradas)
    "started_at": None,
    "finished_at": None,
    "total_projects": 0,
}

MAX_LOG_LINES = 300


def _embed_log(msg: str) -> None:
    """Adiciona linha ao buffer circular de log do embed e ao logger principal."""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    _embed_state["log_lines"].append(line)
    if len(_embed_state["log_lines"]) > MAX_LOG_LINES:
        _embed_state["log_lines"] = _embed_state["log_lines"][-MAX_LOG_LINES:]
    logger.info(f"[EMBED] {msg}")
    _bus.emit("embed.log.appended", {})

rag.log_callback = _embed_log


# ═══════════════════════════════════════════════════════════════════════════════
# CORE DE INDEXAÇÃO (com atualização de estado + retry)
# ═══════════════════════════════════════════════════════════════════════════════

def _collect_files_sync(abs_path: str, project_root: str, extension: str = None) -> list[str]:
    """Coleta todos os caminhos absolutos de arquivos elegíveis para indexação."""
    settings = rag.config.get_all()
    vision_cfg = settings["vision"]
    image_exts = set(vision_cfg.get("allowed_image_extensions", []))
    
    eligible_files = []
    for root, dirs, files in os.walk(abs_path):
        if not _embed_state["running"]:
            break
        # Poda diretórios ignorados in-place
        dirs[:] = [d for d in dirs if not rag.config.is_ignored(os.path.join(root, d), project_root)]
        for file in files:
            file_path = os.path.join(root, file)
            file_ext = os.path.splitext(file)[1].lower()
            
            # Imagens são completamente ignoradas na indexação normal de pastas
            if file_ext in image_exts:
                continue
                
            if not rag.config.is_ignored(file_path, project_root):
                if extension and not file.lower().endswith(extension.lower()):
                    continue
                eligible_files.append(file_path)
    return eligible_files


async def _walk_and_index_async(
    project_id: str,
    abs_path: str,
    project_root: str,
    extension: str = None,
    max_retries: int = 2,
) -> dict:
    """Core assíncrono de indexação rodando no Event Loop principal de forma cooperativa."""
    settings = rag.config.get_all()
    vision_cfg = settings["vision"]
    image_exts = set(vision_cfg.get("allowed_image_extensions", []))

    count = skipped = cached = vision_count = errors = 0
    retry_queue = []  # arquivos que falharam na primeira tentativa

    _embed_state["current_project"] = project_id
    _embed_log(f"Início: {project_id} | {abs_path}")

    # ── PRE-SCAN RÁPIDO PARA ESTATÍSTICAS ─────────────────────────────────────
    _embed_log("Executando pré-scan de arquivos elegíveis...")
    eligible_files = await asyncio.to_thread(_collect_files_sync, abs_path, project_root, extension)
    
    _embed_state["total_expected"] = len(eligible_files)
    
    # ⟲ GARBAGE COLLECTION (Apenas se for escaneamento global do projeto) ⟲
    if os.path.abspath(abs_path) == os.path.abspath(project_root):
        deleted_ghosts = await asyncio.to_thread(rag.cleanup_deleted_files, project_id, eligible_files)
        if deleted_ghosts > 0:
            _embed_log(f"Sincronização: {deleted_ghosts} fantasmas removidos do banco.")
    _embed_log(f"Pré-scan concluído: {len(eligible_files)} arquivos elegíveis.")

    # ── INDEXAÇÃO REAL ────────────────────────────────────────────────────────
    for file_path in eligible_files:
        if not _embed_state["running"]:
            _embed_log(f"Cancelado em: {project_id}")
            break

        _embed_state["current_file"] = os.path.relpath(file_path, project_root)
        _embed_state["current_folder"] = os.path.dirname(file_path)
        _bus.emit("embed.file.processing", {})

        # Serializa via ModelGuard de forma granular para esta chamada específica
        async with get_model_guard().acquire("batch_embed", kind="embed"):
            try:
                file_ext = os.path.splitext(file_path)[1].lower()

                # Imagens: só se Vision estiver ativo
                if file_ext in image_exts:
                    file_abs = os.path.abspath(file_path)
                    is_auto_folder = any(
                        file_abs.startswith(os.path.abspath(f) + os.sep)
                        for f in vision_cfg.get("auto_index_folders", [])
                    )
                    if vision_cfg.get("auto_index_images", False) or is_auto_folder:
                        await asyncio.to_thread(rag.index_image, file_path, project_id)
                        vision_count += 1
                        count += 1
                        _embed_state["stats"]["new"] += 1
                        _embed_state["stats_by_ext"][file_ext] = _embed_state["stats_by_ext"].get(file_ext, 0) + 1
                    else:
                        skipped += 1
                        rag.update_state(stats_inc={"skipped": 1})
                    continue

                result = await asyncio.to_thread(rag.index_file_by_path, file_path, project_id, session_active=True)
                if "Cache Hit" in result:
                    cached += 1
                    _embed_state["stats"]["cached"] += 1
                else:
                    count += 1
                    _embed_state["stats"]["new"] += 1
                    _embed_state["stats_by_ext"][file_ext] = _embed_state["stats_by_ext"].get(file_ext, 0) + 1

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Falha ao indexar {file_path}: {error_msg[:120]}")
                retry_queue.append({
                    "file": file_path,
                    "error": error_msg,
                    "project_id": project_id,
                })
                errors += 1
                _embed_state["stats"]["errors"] += 1

            # LOOKAHEAD DO MODEL GUARD: descarrega proativamente se houver tarefa de tipo diferente aguardando
            next_kind = get_model_guard().peek_next_kind()
            if next_kind is not None and next_kind != "embed":
                _embed_log(f"DEBUG: Lookahead detectou próxima tarefa de kind '{next_kind}'. Descarregando VRAM...")
                await asyncio.to_thread(rag.ollama.unload_models)

    # ── RETRY AUTOMÁTICO ──────────────────────────────────────────────────────
    if retry_queue and max_retries > 0:
        _embed_log(f"Retry: {len(retry_queue)} arquivo(s) com falha em '{project_id}'")
        retry_success = 0
        still_failed = []

        for item in retry_queue:
            if not _embed_state["running"]:
                break

            async with get_model_guard().acquire("batch_embed", kind="embed"):
                try:
                    result = await asyncio.to_thread(rag.index_file_by_path, item["file"], project_id, session_active=True)
                    if result:
                        file_ext = os.path.splitext(item["file"])[1].lower()
                        retry_success += 1
                        errors -= 1
                        _embed_state["stats"]["errors"] -= 1
                        count += 1
                        _embed_state["stats"]["new"] += 1
                        _embed_state["stats_by_ext"][file_ext] = _embed_state["stats_by_ext"].get(file_ext, 0) + 1
                except Exception as e:
                    still_failed.append({**item, "error": str(e)})

                next_kind = get_model_guard().peek_next_kind()
                if next_kind != "embed":
                    await asyncio.to_thread(rag.ollama.unload_models)

        if retry_success:
            _embed_log(f"Retry recuperou {retry_success}/{len(retry_queue)} arquivo(s)")

        if still_failed:
            _embed_state["error_files"].extend(still_failed)
            _embed_log(f"Ainda com falha após retry: {len(still_failed)} arquivo(s)")
    else:
        _embed_state["error_files"].extend(retry_queue)

    return {
        "new": count,
        "cached": cached,
        "skipped": skipped,
        "vision": vision_count,
        "errors": errors,
    }


# ─── Worker de background ──────────────────────────────────────────────────────

async def _batch_embed_worker(project_ids_initial: list, force: bool = False) -> None:
    """Worker assíncrono que roda como background task.

    Processa a fila dinâmica (_embed_state["queue"]) até ela esvaziar ou
    o embed ser cancelado.
    """
    global _embed_state

    # Inicializa estado
    _embed_state["running"] = True
    _embed_state["canceled"] = False
    _embed_state["started_at"] = datetime.datetime.now().isoformat()
    _embed_state["finished_at"] = None
    _embed_state["stats"] = {"new": 0, "cached": 0, "skipped": 0, "errors": 0}
    _embed_state["error_files"] = []
    _embed_state["log_lines"] = []
    _embed_state["completed"] = []
    _embed_state["current_file"] = None
    _embed_state["current_folder"] = None
    _embed_state["current_project"] = None

    with _telemetry.activity():
        try:
            projects = load_projects()

            # Carrega progresso de sessão anterior para retomada automática
            progress = {} if force else load_batch_progress()
            completed_prev = set(progress.get("completed", []))
            results = progress.get("results", {})

            # Popula fila com os projetos iniciais
            if project_ids_initial is None:
                project_ids_initial = list(projects.keys())

            for pid in project_ids_initial:
                if pid in projects:
                    _embed_state["queue"].append({
                        "kind": "project",
                        "project_id": pid,
                        "project_root": projects[pid],
                        "force": force,
                    })

            _embed_state["total_projects"] = len(_embed_state["queue"])
            _embed_log(
                f"Worker iniciado | {_embed_state['total_projects']} projeto(s) na fila"
                + (f" | Retomando: {sorted(completed_prev)}" if completed_prev else "")
            )

            while _embed_state["queue"] and _embed_state["running"]:
                item = _embed_state["queue"].pop(0)
                kind = item.get("kind", "project")
                project_id = item["project_id"]
                project_root = item.get("project_root")
                item_force = item.get("force", force)
                
                if kind == "project":
                    # Pula projetos já concluídos (a menos que force)
                    if project_id in completed_prev and not item_force:
                        prev = results.get(project_id, {})
                        _embed_log(
                            f"SKIP {project_id}: já indexado "
                            f"({prev.get('new', '?')} novos, {prev.get('cached', '?')} cache)"
                        )
                        if project_id not in _embed_state["completed"]:
                            _embed_state["completed"].append(project_id)
                        continue

                    if not os.path.isdir(project_root):
                        _embed_log(f"ERRO {project_id}: caminho inválido '{project_root}'")
                        results[project_id] = {"status": "erro", "message": "caminho inválido"}
                        save_batch_progress({"completed": sorted(completed_prev), "results": results})
                        continue

                    _embed_log(f"Processando: {project_id} | {project_root}")

                    try:
                        # HEARTBEAT: Antes da indexação
                        _embed_log(f"DEBUG: Iniciando _walk_and_index_async para {project_id}")
                        stats = await asyncio.wait_for(
                            _walk_and_index_async(project_id, project_root, project_root),
                            timeout=3600  # Timeout de 1 hora por projeto
                        )
                        
                        # HEARTBEAT: Após indexação, antes de descarregar VRAM
                        _embed_log(f"DEBUG: Indexação concluída. Solicitando descarga de VRAM para {project_id}")
                        await asyncio.to_thread(rag.ollama.unload_models)
                        _embed_log(f"DEBUG: VRAM descarregada com sucesso.")

                        if project_id not in _embed_state["completed"]:
                            _embed_state["completed"].append(project_id)
                        completed_prev.add(project_id)
                        results[project_id] = {"status": "ok", **stats}
                        save_batch_progress({"completed": sorted(completed_prev), "results": results})

                        _embed_log(
                            f"OK {project_id}: {stats['new']} novos | "
                            f"{stats['cached']} cache | "
                            f"{stats['skipped']} ignorados | "
                            f"{stats['errors']} erros"
                        )

                    except Exception as e:
                        _embed_log(f"FALHA {project_id}: {str(e)[:120]}")
                        results[project_id] = {"status": "erro", "message": str(e)}
                        save_batch_progress({"completed": sorted(completed_prev), "results": results})
                        # Continua para o próximo projeto
                elif kind == "directory":
                    path = item["path"]
                    extension = item.get("extension")
                    _embed_log(f"Processando diretório: {path} | Projeto: {project_id}")
                    try:
                        stats = await asyncio.wait_for(
                            _walk_and_index_async(project_id, path, project_root, extension),
                            timeout=3600
                        )
                        _embed_log(f"OK diretório: {path} ({stats['new']} novos, {stats['vision']} vision)")
                    except Exception as e:
                        _embed_log(f"FALHA diretório {path}: {str(e)[:120]}")

                elif kind == "file":
                    path = item["path"]
                    _embed_log(f"Processando arquivo: {path} | Projeto: {project_id}")
                    try:
                        async with get_model_guard().acquire("index_file", kind="embed"):
                            result = await asyncio.to_thread(rag.index_file_by_path, path, project_id)
                        _embed_log(f"OK arquivo: {path} | {result}")
                    except Exception as e:
                        _embed_log(f"FALHA arquivo {path}: {str(e)[:120]}")

                elif kind == "image":
                    path = item["path"]
                    _embed_log(f"Processando imagem: {path} | Projeto: {project_id}")
                    try:
                        async with get_model_guard().acquire("index_image", kind="vision"):
                            await asyncio.to_thread(rag.index_image, path, project_id)
                        _embed_log(f"OK imagem: {path}")
                    except Exception as e:
                        _embed_log(f"FALHA imagem {path}: {str(e)[:120]}")

        finally:
            await asyncio.to_thread(rag.ollama.unload_models)
            _embed_state["running"] = False
            _embed_state["current_project"] = None
            _embed_state["current_file"] = None
            _embed_state["current_folder"] = None
            _embed_state["finished_at"] = datetime.datetime.now().isoformat()

            # Limpa progresso apenas se concluiu tudo sem cancelamento
            pending_queue = list(_embed_state["queue"])
            if not pending_queue and not _embed_state["canceled"]:
                try:
                    if os.path.exists(BATCH_PROGRESS_FILE):
                        os.remove(BATCH_PROGRESS_FILE)
                except Exception:
                    pass

            total_done = len(_embed_state["completed"])
            _embed_log(
                f"Worker finalizado | "
                f"Concluídos: {total_done} | "
                f"Novos: {_embed_state['stats']['new']} | "
                f"Erros: {_embed_state['stats']['errors']}"
            )

            # Sinaliza fim do trabalho ao dashboard com flush imediato (ignora throttle).
            try:
                _inventory.invalidate()
                _bus.emit("embed.batch.finished", {})
                payload = _telemetry.snapshot(
                    embed_state=_embed_state,
                    rag_state=rag.state,
                    batch_progress=_batch_progress_cache,
                    server_extra=_server_extra,
                )
                _telemetry.flush(payload)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# FERRAMENTAS: Gestão de Projetos
# ═══════════════════════════════════════════════════════════════════════════════

@mcp_tool_with_logging
async def register_project(project_id: str, path: str) -> str:
    """Registra um projeto e valida seu caminho. Use antes de indexar qualquer pasta."""
    if not os.path.exists(path):
        return f"Erro: O caminho '{path}' não existe."
    if not os.path.isdir(path):
        return f"Erro: '{path}' não é um diretório."
    save_project(project_id, path)
    logger.info(f"Projeto '{project_id}' registrado: {path}")
    return f"Projeto '{project_id}' registrado com sucesso em: {path}"


@mcp_tool_with_logging
async def list_projects() -> str:
    """Lista todos os projetos registrados e seus caminhos."""
    projects = load_projects()
    if not projects:
        return "Nenhum projeto registrado."
    lines = [f"Projetos registrados ({len(projects)}):"]
    for pid, path in sorted(projects.items()):
        exists = "✓" if os.path.isdir(path) else "✗ (caminho inválido)"
        lines.append(f"  [{exists}] {pid}: {path}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# FERRAMENTAS: Indexação
# ═══════════════════════════════════════════════════════════════════════════════

def _queue_task(task: dict):
    global _embed_task
    _embed_state["queue"].append(task)
    if _embed_task is None or _embed_task.done():
        _embed_task = asyncio.create_task(_batch_embed_worker([], False))



@mcp_tool_with_logging
async def index_file(path: str) -> str:
    """Indexa um arquivo individual (.rs, .cpp, .h, .lua, .py, .md, .pdf, etc.).
    Detecta o projeto automaticamente pelo caminho."""
    status = await asyncio.to_thread(rag.ollama.check_connection)
    if not status["connected"]:
        return f"Erro: Ollama offline em {rag.ollama.base_url}"

    if not os.path.exists(path):
        return f"Erro: Arquivo '{path}' não encontrado."
    project_id = get_project_for_path(path)
    if not project_id:
        return f"Erro: '{path}' não pertence a nenhum projeto registrado."
    
    _queue_task({
        "kind": "file",
        "project_id": project_id,
        "path": path
    })
    return f"Arquivo '{path}' adicionado à fila de indexação (background)."


@mcp_tool_with_logging
async def index_directory(path: str, extension: str = None) -> str:
    """Indexa um diretório completo respeitando filtros de extensão e .gitignore.

    Args:
        path: Diretório a indexar (deve pertencer a um projeto registrado).
        extension: Opcional. Filtra por extensão (ex: '.rs', '.cpp').
    """
    status = await asyncio.to_thread(rag.ollama.check_connection)
    if not status["connected"]:
        return (
            f"Erro: Ollama não está disponível em {rag.ollama.base_url}. "
            f"Inicie o Ollama antes de indexar. Detalhe: {status.get('error', 'sem detalhes')}"
        )

    abs_path = os.path.abspath(path)
    if not os.path.isdir(abs_path):
        return f"Erro: Diretório inválido: '{path}'"

    project_id = get_project_for_path(abs_path)
    if not project_id:
        return (
            f"Erro: '{abs_path}' não pertence a nenhum projeto registrado. "
            f"Use register_project primeiro."
        )

    projects = load_projects()
    project_root = projects.get(project_id)

    _queue_task({
        "kind": "directory",
        "project_id": project_id,
        "project_root": project_root,
        "path": abs_path,
        "extension": extension
    })
    
    return f"Diretório '{abs_path}' adicionado à fila de indexação (background)."


@mcp_tool_with_logging
async def batch_index_projects(
    project_ids: list = None,
    force: bool = False,
    background: bool = True,
) -> str:
    """Indexa múltiplos projetos sequencialmente com progresso persistido.

    Por padrão roda em BACKGROUND: o servidor MCP continua respondendo enquanto
    o embed acontece. Use get_embed_status() para monitorar o progresso em
    tempo real.

    Se chamado enquanto embed já está em andamento, os novos projetos são
    ADICIONADOS À FILA e serão processados na sequência.

    O cache MD5 garante que arquivos já indexados não sejam reprocessados.
    Em caso de crash, execute novamente para retomar de onde parou.

    Args:
        project_ids: Lista de IDs a indexar. None = todos os projetos registrados.
                     Ex: ["MCP Rust Star", "Rust Star", "FoxOT", "FoxClient"]
        force: Se True, reprocessa projetos já concluídos anteriormente.
        background: True (padrão) = roda em background, retorna imediatamente.
                    False = bloqueia até concluir (útil para scripts/testes).
    """
    global _embed_task

    # ── PRE-FLIGHT ────────────────────────────────────────────────────────────
    status = rag.ollama.check_connection()
    if not status["connected"]:
        return (
            f"Erro: Ollama não disponível. Inicie antes de indexar.\n"
            f"Detalhe: {status.get('error', '')}"
        )

    projects = load_projects()
    if not projects:
        return "Nenhum projeto registrado. Use register_project primeiro."

    if project_ids is None:
        target_ids = list(projects.keys())
    else:
        unknown = [p for p in project_ids if p not in projects]
        if unknown:
            return (
                f"Erro: Projetos não registrados: {unknown}\n"
                f"Disponíveis: {list(projects.keys())}"
            )
        target_ids = project_ids

    # ── SE JÁ ESTÁ RODANDO: adiciona à fila ──────────────────────────────────
    if _embed_state["running"]:
        added = []
        for pid in target_ids:
            if pid in projects:
                _embed_state["queue"].append({
                    "kind": "project",
                    "project_id": pid,
                    "project_root": projects[pid],
                    "force": force,
                })
                added.append(pid)
        queue_names = [q["project_id"] for q in _embed_state["queue"]]
        return (
            f"⟳ Embed já em andamento: {_embed_state['current_project']}\n"
            f"Projetos adicionados à fila: {added}\n"
            f"Fila completa: {queue_names}\n"
            f"Use get_embed_status() para monitorar."
        )

    # ── MODO SÍNCRONO (bloqueia) ──────────────────────────────────────────────
    if not background:
        _embed_state["queue"] = []
        await _batch_embed_worker(target_ids, force)
        s = _embed_state["stats"]
        return (
            f"Embed síncrono concluído!\n"
            f"  ✓ Novos:     {s['new']}\n"
            f"  ⊙ Cache:     {s['cached']}\n"
            f"  ○ Ignorados: {s['skipped']}\n"
            f"  ✗ Erros:     {s['errors']}\n"
            f"  Projetos: {_embed_state['completed']}"
        )

    # ── MODO BACKGROUND (padrão) ──────────────────────────────────────────────
    _embed_state["queue"] = []  # Limpa fila antiga antes de iniciar

    _embed_task = asyncio.create_task(_batch_embed_worker(target_ids, force))

    # Pequeno yield para o worker inicializar
    await asyncio.sleep(0.05)

    progress = load_batch_progress()
    completed_prev = progress.get("completed", [])
    skip_count = len([p for p in target_ids if p in completed_prev and not force])

    return (
        f"✓ Embed iniciado em background!\n"
        f"  Projetos na fila: {target_ids}\n"
        f"  Force reindex: {force}\n"
        + (f"  (Pulando {skip_count} já indexados — use force=True para reprocessar)\n"
           if skip_count else "")
        + f"\nUse get_embed_status() para acompanhar o progresso em tempo real.\n"
        f"Use cancel_embed() para cancelar se necessário."
    )


@mcp_tool_with_logging
async def scan_extensions(project_ids: list = None) -> str:
    """Escaneia projetos e lista todas as extensões encontradas — SEM indexar nada.

    Use ANTES de batch_index_projects para confirmar quais tipos de arquivo
    serão processados. Mostra o que será indexado vs. o que já está na lista
    de ignorados. Arquivos sem extensão são listados separadamente.

    Args:
        project_ids: Lista de projetos a escanear. None = todos registrados.
    """
    projects = load_projects()
    if not projects:
        return "Nenhum projeto registrado."

    if project_ids is None:
        target_ids = list(projects.keys())
    else:
        unknown = [p for p in project_ids if p not in projects]
        if unknown:
            return f"Projetos não registrados: {unknown}\nDisponíveis: {list(projects.keys())}"
        target_ids = project_ids

    settings = rag.config.get_all()
    already_ignored = set(settings.get("indexing", {}).get("ignored_extensions", []))

    ext_by_project: dict[str, Counter] = {}
    no_ext_files: list[str] = []
    total_files = 0

    for pid in target_ids:
        project_root = projects[pid]
        if not os.path.isdir(project_root):
            continue

        ext_by_project[pid] = Counter()

        for root, dirs, files in os.walk(project_root):
            dirs[:] = [
                d for d in dirs
                if not rag.config.is_ignored(os.path.join(root, d), project_root)
            ]
            for fname in files:
                file_path = os.path.join(root, fname)
                if rag.config.is_ignored(file_path, project_root):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext:
                    ext_by_project[pid][ext] += 1
                else:
                    no_ext_files.append(
                        f"[{pid}] {os.path.relpath(file_path, project_root)}"
                    )
                total_files += 1

        # Cede controle ao event loop
        await asyncio.sleep(0)

    # Agrega todos os projetos
    all_exts: Counter = Counter()
    for c in ext_by_project.values():
        all_exts.update(c)

    will_index = {ext: cnt for ext, cnt in all_exts.items() if ext not in already_ignored}
    will_skip = {ext: cnt for ext, cnt in all_exts.items() if ext in already_ignored}

    lines = [
        f"═══ SCAN DE EXTENSÕES ═══",
        f"Projetos: {target_ids}",
        f"Total de arquivos elegíveis: {total_files}",
        "",
    ]

    if will_index:
        total_to_index = sum(will_index.values())
        lines.append(
            f"✓ SERÃO INDEXADOS ({len(will_index)} tipos, {total_to_index} arquivo(s)):"
        )
        for ext, cnt in sorted(will_index.items(), key=lambda x: -x[1]):
            lines.append(f"   {ext:15}  {cnt:6} arquivo(s)")
    else:
        lines.append("(Nenhum arquivo para indexar com os filtros atuais)")

    if no_ext_files:
        lines.append(
            f"\n⚠ ARQUIVOS SEM EXTENSÃO ({len(no_ext_files)}) — "
            f"serão indexados se forem texto legível:"
        )
        for f in no_ext_files[:20]:
            lines.append(f"   {f}")
        if len(no_ext_files) > 20:
            lines.append(f"   ... e mais {len(no_ext_files) - 20}")

    if will_skip:
        total_skip = sum(will_skip.values())
        lines.append(
            f"\n○ JÁ NA LISTA DE IGNORADOS ({len(will_skip)} tipos, {total_skip} arquivo(s)):"
        )
        for ext, cnt in sorted(will_skip.items(), key=lambda x: -x[1]):
            lines.append(f"   {ext:15}  {cnt:6} arquivo(s)")

    lines += [
        "",
        "─" * 60,
        "Para ignorar extensões indesejadas ANTES de indexar:",
        '  update_indexing_settings(ignored_extensions=[".ext1", ".ext2", ...])',
        "",
        "Quando a lista estiver correta:",
        "  batch_index_projects()  ← inicia embed em background",
    ]

    return "\n".join(lines)


@mcp_tool_with_logging
async def get_embed_status() -> str:
    """Retorna o status atual do embed em background e as últimas linhas de log (Não-Bloqueante)."""
    # Cria uma cópia local rápida do estado para evitar contenção de thread
    state = _embed_state.copy()
    
    # Se o worker não está rodando na memória, tenta carregar do disco
    if not state.get("running") and not state.get("started_at"):
        progress = load_batch_progress()
        if progress:
            completed = progress.get("completed", [])
            results = progress.get("results", {})
            return (
                f"Nenhum embed ativo na memória.\n"
                f"Progresso persistido no disco:\n"
                f"  Concluídos: {completed}\n"
                f"Use batch_index_projects() para retomar."
            )
        return "Nenhum embed ativo."

    lines = []
    
    # Status Visual
    status_icon = "⟳" if state["running"] else "✓"
    status_text = "EM ANDAMENTO" if state["running"] else "CONCLUÍDO"
    lines.append(f"{status_icon} STATUS: {status_text}")

    # Tempo Decorrido
    if state["started_at"]:
        try:
            started_dt = datetime.datetime.fromisoformat(state["started_at"])
            elapsed = datetime.datetime.now() - started_dt
            lines.append(f"Duração: {str(elapsed).split('.')[0]}")
        except: pass

    # Progresso Atual
    if state["current_project"]:
        lines.append(f"Projeto: {state['current_project']}")
    if state["current_file"]:
        # Mostra apenas o final do caminho para economizar espaço
        fname = state["current_file"].split(os.sep)[-1]
        lines.append(f"Arquivo: {fname}")

    # Estatísticas Rápidas
    s = state["stats"]
    lines.append(
        f"\nEstatísticas:\n"
        f"  ✓ {s['new']} novos | ⊙ {s['cached']} cache | ✗ {s['errors']} erros"
    )

    # Log Recente (Lido direto do arquivo para evitar lock de memória)
    try:
        log_path = "logs/mcp_error.log"
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                # Lê as últimas 10 linhas de forma eficiente
                all_lines = f.readlines()
                log_tail = all_lines[-10:]
                if log_tail:
                    lines.append("\nLog recente:")
                    for line in log_tail:
                        # Tenta remover o timestamp longo para facilitar leitura
                        parts = line.split(" - ")
                        clean_line = parts[-1].strip() if len(parts) > 1 else line.strip()
                        lines.append(f"  > {clean_line}")
    except:
        lines.append("\n(Log inacessível no momento)")

    return "\n".join(lines)


@mcp_tool_with_logging
async def cancel_embed() -> str:
    """Cancela o embed em background (para após o arquivo atual terminar).

    O progresso já salvo é mantido — você pode retomar depois com
    batch_index_projects() (projetos concluídos serão pulados automaticamente).
    """
    global _embed_task

    if not _embed_state["running"]:
        return "Nenhum embed em andamento para cancelar."

    _embed_state["running"] = False
    _embed_state["canceled"] = True
    _embed_state["queue"] = []  # Esvazia fila
    _bus.emit("embed.cancelled", {})

    # Aguarda o arquivo atual terminar (não interrompe no meio)
    await asyncio.sleep(1.0)

    s = _embed_state["stats"]
    return (
        f"✓ Cancelamento solicitado. O embed parou após o arquivo atual.\n"
        f"\nResumo até o cancelamento:\n"
        f"  Projetos concluídos: {_embed_state['completed']}\n"
        f"  Novos indexados: {s['new']}\n"
        f"  Erros: {s['errors']}\n"
        f"\nExecute batch_index_projects() para retomar de onde parou."
    )


@mcp_tool_with_logging
@with_model_guard(kind="embed")
async def retry_failed_files() -> str:
    """Re-indexa arquivos que falharam durante o último embed.

    Use get_embed_status() para ver a lista de arquivos com erro antes de usar.
    Não pode ser executado enquanto embed está em andamento.
    """
    error_files = list(_embed_state.get("error_files", []))

    if not error_files:
        return "Nenhum arquivo com falha registrado. Use get_embed_status() para verificar."

    if _embed_state["running"]:
        return (
            "Embed em andamento. Aguarde concluir antes de executar retry.\n"
            "Ou use cancel_embed() para cancelar primeiro."
        )

    total = len(error_files)
    success = 0
    still_failed = []

    _embed_log(f"Retry manual iniciado: {total} arquivo(s)")

    for item in error_files:
        try:
            result = rag.index_file_by_path(item["file"], item["project_id"])
            if result:
                success += 1
                _embed_state["stats"]["errors"] = max(0, _embed_state["stats"]["errors"] - 1)
                _embed_state["stats"]["new"] += 1
        except Exception as e:
            still_failed.append({**item, "error": str(e)})

    _embed_state["error_files"] = still_failed
    _embed_log(f"Retry manual concluído: {success}/{total} recuperados")

    lines = [
        f"Retry concluído:\n"
        f"  ✓ Recuperados: {success}/{total}\n"
        f"  ✗ Ainda falham: {len(still_failed)}"
    ]
    if still_failed:
        lines.append("\nArquivos ainda com erro:")
        for ef in still_failed[:15]:
            lines.append(f"  [{ef['project_id']}] {os.path.basename(ef['file'])}: {ef['error'][:80]}")
        if len(still_failed) > 15:
            lines.append(f"  ... e mais {len(still_failed) - 15}")

    return "\n".join(lines)


@mcp_tool_with_logging
@with_model_guard(kind="vision")
async def index_image(path: str) -> str:
    """Indexa uma imagem manualmente via Vision (PNG/JPG).
    Detecta o projeto automaticamente pelo caminho."""
    if not os.path.exists(path):
        return f"Erro: Imagem '{path}' não encontrada."
    project_id = get_project_for_path(path)
    if not project_id:
        return f"Erro: '{path}' não pertence a nenhum projeto registrado."
    _queue_task({
        "kind": "image",
        "project_id": project_id,
        "path": path
    })
    return f"Imagem '{path}' adicionada à fila de indexação (background)."


# ═══════════════════════════════════════════════════════════════════════════════
# FERRAMENTAS: Análise Visual de Screenshots
# ═══════════════════════════════════════════════════════════════════════════════

@mcp_tool_with_logging
@with_model_guard(kind="vision")
async def analyze_screenshot(path: str, save_to_kb: bool = True, context_hint: str = "") -> str:
    """Analisa um screenshot técnico do Rust Star / FoxOT usando Vision.

    Especializado em: erros de compilação Rust, bugs de renderização WGPU,
    logs do servidor, output de cargo, crash dumps, estado do mapa, etc.

    Args:
        path: Caminho da imagem (PNG/JPG).
        save_to_kb: Se True, salva a análise na base de conhecimento para busca futura.
        context_hint: Contexto adicional sobre o que você espera encontrar na imagem.
    """
    if not os.path.exists(path):
        return f"Erro: Arquivo '{path}' não encontrado."

    ext = os.path.splitext(path)[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
        return f"Erro: Formato '{ext}' não suportado. Use PNG, JPG ou JPEG."

    status = rag.ollama.check_connection()
    if not status["connected"]:
        return f"Erro: Ollama offline. {status.get('error', '')}"
    if not status.get("rag_model_ok"):
        return f"Erro: Modelo RAG '{rag.ollama.rag_model}' não disponível no Ollama."

    logger.info(f"Analisando screenshot: {path}")

    if context_hint:
        import base64
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        user_msg = (
            f"Contexto fornecido pelo usuário: {context_hint}\n\n"
            "Analise esta imagem e forneça um relatório técnico detalhado."
        )
        from src.ollama_client import _SYSTEM_PROMPT_VISION
        response = rag.ollama.client.chat(
            model=rag.ollama.rag_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT_VISION},
                {"role": "user", "content": user_msg, "images": [b64]},
            ],
            options={"num_ctx": rag.ollama.num_ctx},
        )
        rag.ollama._unload_model(rag.ollama.rag_model, is_chat=True)
        description = response["message"]["content"]
    else:
        description = rag.ollama.describe_image(os.path.abspath(path))

    if not description:
        return "Erro: Não foi possível gerar análise. Verifique se o modelo suporta Vision."

    kb_status = ""
    if save_to_kb:
        project_id = get_project_for_path(path)
        if not project_id:
            projects = load_projects()
            project_id = next(iter(projects), None)

        if project_id:
            file_name = os.path.basename(path)
            abs_path = os.path.abspath(path)
            enriched_text = (
                f"SCREENSHOT ANALISADO: {file_name}\n"
                f"LOCALIZAÇÃO: {abs_path}\n"
                f"PROJETO: {project_id}\n"
                f"CONTEXTO DO USUÁRIO: {context_hint or 'Não informado'}\n\n"
                f"ANÁLISE TÉCNICA:\n{description}"
            )
            rag.index_text(enriched_text, abs_path, project_id)
            kb_status = f"\n\n[✓ Análise salva na base de conhecimento | Projeto: {project_id}]"
        else:
            kb_status = "\n\n[⚠ Nenhum projeto registrado. Análise não salva na KB.]"

    return f"=== ANÁLISE DO SCREENSHOT: {os.path.basename(path)} ===\n\n{description}{kb_status}"


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: Formatação de resultados RAW
# ═══════════════════════════════════════════════════════════════════════════════

def _format_raw_response(result: dict, scope: str) -> str:
    """Formata o resultado de search_raw() para retorno nas ferramentas MCP."""

    # Cache hit — retorna conteúdo do arquivo salvo
    if result.get("cached"):
        cached_file = result.get("cached_file", "?")
        cached_content = result.get("cached_content", "")
        return (
            f"⚡ [CACHE HIT] Resultado recuperado instantaneamente.\n"
            f"📄 Arquivo: {cached_file}\n\n"
            f"{cached_content}"
        )

    fragments = result.get("fragments", [])
    discarded = result.get("discarded", [])
    threshold = result.get("threshold", 0.75)
    error = result.get("error")

    if error:
        return f"Erro na busca: {error}"

    if not fragments and not discarded:
        return f"=== BUSCA [{scope}] ===\n\nNenhum fragmento encontrado na base de conhecimento."

    lines = [
        f"=== BUSCA [{scope}] | {len(fragments)} fragmentos (threshold: {threshold}) ===",
        ""
    ]

    for i, frag in enumerate(fragments, 1):
        meta = frag.get("metadata", {})
        source = meta.get("source", "desconhecido")
        basename = os.path.basename(source)
        category = meta.get("category", "N/A")
        tags = meta.get("tags", [])
        distance = frag.get("distance", 0)

        lines.extend([
            f"[{i}/{len(fragments)}] 📁 {basename} | distância: {distance:.4f} | {category}",
            f"Fonte: {source}",
            f"Tags: [{', '.join(tags)}]",
            "────────────────────",
            frag.get("content", "").strip(),
            "────────────────────",
            ""
        ])

    if discarded:
        lines.append(f"⊘ {len(discarded)} fragmentos descartados (distância > {threshold}):")
        for d in discarded:
            d_meta = d.get("metadata", {})
            d_source = os.path.basename(d_meta.get("source", "?"))
            d_dist = d.get("distance", 0)
            lines.append(f"  • {d_source} (distância: {d_dist:.4f})")
        lines.append("")

    # Indica onde o resultado bruto foi salvo
    project_id = result.get("project_id")
    folder = project_id if project_id else "global"
    lines.append(f"📄 Resultado salvo em: logs/rag_history/{folder}/")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# FERRAMENTAS: Busca RAG
# ═══════════════════════════════════════════════════════════════════════════════

async def _background_rag_task(question: str, project_id: str, custom_filename: str, tool_name: str) -> None:
    """Executa a busca RAG em background respeitando o ModelGuard serializado."""
    guard = get_model_guard()
    try:
        async with guard.acquire(tool_name, kind="embed"):
            # Executa a busca vetorial (que realiza a geração do embedding via Ollama e salva em disco)
            await asyncio.to_thread(rag.search_raw, question, project_id, None, None, custom_filename)
            logger.info(f"✓ Busca RAG em background [{tool_name}] concluída e salva como {custom_filename}")
    except Exception as e:
        logger.error(f"Erro na busca RAG em background [{tool_name}]: {e}")


def _write_rag_placeholder(folder: str, file_name: str, question: str, project_id: str) -> None:
    """Escreve um arquivo placeholder temporário para sinalizar que o processamento está em andamento."""
    try:
        target_dir = os.path.join(rag.history_dir, folder)
        os.makedirs(target_dir, exist_ok=True)
        file_path = os.path.join(target_dir, file_name)
        
        now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        content = (
            f"# ⏳ Buscando Resultados RAG...\n\n"
            f"A busca RAG está sendo processada em background. Por favor, aguarde e verifique este arquivo novamente em alguns segundos para visualizar os resultados.\n\n"
            f"- **Pergunta**: {question}\n"
            f"- **Projeto**: {project_id if project_id else 'global'}\n"
            f"- **Iniciado em**: {now_str}\n"
        )
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Placeholder RAG criado em: {file_path}")
    except Exception as e:
        logger.error(f"Erro ao criar placeholder RAG: {e}")


@mcp_tool_with_logging
async def ask_knowledge_base(question: str, project_id: str = None) -> str:
    """Consulta a base de conhecimento com RAG. Retorna resposta com citação de fontes.

    Args:
        question: Sua pergunta técnica sobre código, arquitetura, etc.
        project_id: Opcional. Filtra por projeto (ex: 'Rust Star', 'FoxOT', 'FoxClient').
                    Se omitido, busca em todos os projetos.
    """
    _server_extra["last_query"] = {
        "question": question[:200],
        "project_id": project_id,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _bus.emit("rag.query.received", {"question": question[:200], "project_id": project_id})

    # Verifica cache existente
    cache_hit = rag._check_raw_cache(question, project_id)
    folder = project_id if project_id else "global"
    save_dir = os.path.abspath(os.path.join(rag.history_dir, folder))
    
    if cache_hit:
        cached_file_path = cache_hit.get("cached_file")
        file_name = os.path.basename(cached_file_path)
    else:
        timestamp = datetime.datetime.now()
        ts_str = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f"query_{ts_str}.md"
        # Cria placeholder imediatamente para evitar "File Not Found"
        _write_rag_placeholder(folder, file_name, question, project_id)
        # Dispara background task
        asyncio.create_task(_background_rag_task(question, project_id, file_name, "ask_knowledge_base"))
        
    return (
        f"Seu pedido esta na fila de processamento, assim que finalizar envido msg avisando!\n"
        f"O resultado vai ser salvo em:\n"
        f"Diretório: {save_dir}\n"
        f"Nome do arquivo: {file_name}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FERRAMENTAS: Busca Avançada por Projeto
# ═══════════════════════════════════════════════════════════════════════════════

@mcp_tool_with_logging
async def search_project_knowledge(project_id: str, question: str) -> str:
    """[FERRAMENTA PRINCIPAL DE BUSCA] Busca isolada em um projeto específico.
    Rápida e precisa. Use sempre que souber em qual projeto está a informação.
    Para cruzar dados de múltiplos projetos, use cross_project_analysis.

    Args:
        project_id: Nome do projeto (ex: 'rust_star', 'foxot', 'foxclient', 'nova_rust').
        question: O que você quer encontrar na base de conhecimento.
    """
    _server_extra["last_query"] = {
        "question": question[:200],
        "project_id": project_id,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _bus.emit("rag.query.received", {"question": question[:200], "project_id": project_id})

    cache_hit = rag._check_raw_cache(question, project_id)
    folder = project_id if project_id else "global"
    save_dir = os.path.abspath(os.path.join(rag.history_dir, folder))
    
    if cache_hit:
        cached_file_path = cache_hit.get("cached_file")
        file_name = os.path.basename(cached_file_path)
    else:
        timestamp = datetime.datetime.now()
        ts_str = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f"query_{ts_str}.md"
        _write_rag_placeholder(folder, file_name, question, project_id)
        asyncio.create_task(_background_rag_task(question, project_id, file_name, "search_project_knowledge"))
        
    return (
        f"Seu pedido esta na fila de processamento, assim que finalizar envido msg avisando!\n"
        f"O resultado vai ser salvo em:\n"
        f"Diretório: {save_dir}\n"
        f"Nome do arquivo: {file_name}"
    )


@mcp_tool_with_logging
async def search_all_projects_knowledge(question: str) -> str:
    """[LENTA] Busca em TODOS os projetos simultaneamente.
    ⚠️ AVISO DE DESEMPENHO: Percorre todas as tabelas do banco sequencialmente.
    O tempo de resposta aumenta com o número de projetos indexados.
    Use apenas quando não souber em qual projeto está a informação.
    Prefira search_project_knowledge quando o projeto for conhecido.

    Args:
        question: O que você quer encontrar (buscado em todos os projetos).
    """
    _server_extra["last_query"] = {
        "question": question[:200],
        "project_id": None,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _bus.emit("rag.query.received", {"question": question[:200], "project_id": None})

    cache_hit = rag._check_raw_cache(question, None)
    folder = "global"
    save_dir = os.path.abspath(os.path.join(rag.history_dir, folder))
    
    if cache_hit:
        cached_file_path = cache_hit.get("cached_file")
        file_name = os.path.basename(cached_file_path)
    else:
        timestamp = datetime.datetime.now()
        ts_str = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f"query_{ts_str}.md"
        _write_rag_placeholder(folder, file_name, question, None)
        asyncio.create_task(_background_rag_task(question, None, file_name, "search_all_projects_knowledge"))
        
    return (
        f"Seu pedido esta na fila de processamento, assim que finalizar envido msg avisando!\n"
        f"O resultado vai ser salvo em:\n"
        f"Diretório: {save_dir}\n"
        f"Nome do arquivo: {file_name}"
    )


@mcp_tool_with_logging
@with_model_guard(kind="embed")
async def cross_project_analysis(searches_json: str, analysis_prompt: str) -> str:
    """Busca em múltiplos projetos e gera análise cruzada dos dados coletados.
    Executa as buscas em fila (uma de cada vez) para não sobrecarregar o Ollama,
    depois combina todos os fragmentos encontrados e gera análise unificada.

    Args:
        searches_json: JSON com lista de buscas por projeto. Formato:
                       [{"project_id": "nome", "query": "o que buscar"}, ...]
                       Exemplo: [{"project_id": "rust_star", "query": "sistema de combate"},
                                 {"project_id": "foxot", "query": "sistema de combate"}]
        analysis_prompt: O que analisar/comparar com os dados coletados.
                         Exemplo: "Compare as diferenças de implementação entre os projetos
                                   e aponte os pontos em comum e as divergências."
    """
    try:
        searches = json.loads(searches_json)
    except json.JSONDecodeError as e:
        return f"Erro: searches_json inválido. Use formato JSON válido.\nDetalhe: {e}"

    result = await asyncio.to_thread(rag.cross_project_analysis, searches, analysis_prompt)

    projects = list(result.get("raw_results", {}).keys())
    response = f"=== ANÁLISE CRUZADA | {len(projects)} projeto(s): {', '.join(projects)} ===\n\n"

    for proj, data in result.get("raw_results", {}).items():
        frags = data.get("fragments_found", 0)
        query = data.get("query", "")
        response += f"  • {proj}: {frags} fragmento(s) encontrado(s) (busca: '{query}')\n"

    response += f"\n=== ANÁLISE ===\n\n{result['analysis']}\n"
    return response


# ═══════════════════════════════════════════════════════════════════════════════
# FERRAMENTAS: Fontes Indexadas
# ═══════════════════════════════════════════════════════════════════════════════

@mcp_tool_with_logging
async def list_indexed_sources(project_id: str = None) -> str:
    """Lista todos os arquivos-fonte únicos indexados na base de conhecimento.

    Args:
        project_id: Opcional. Filtra por projeto específico.
    """
    sources = await asyncio.to_thread(rag.list_indexed_sources, project_id)
    if not sources:
        scope = f"projeto '{project_id}'" if project_id else "qualquer projeto"
        return f"Nenhuma fonte indexada encontrada para {scope}."

    by_project: dict[str, list] = {}
    for s in sources:
        pid = s.get("project_id", "desconhecido")
        by_project.setdefault(pid, []).append(s.get("source", "?"))

    target = f"projeto '{project_id}'" if project_id else "todos os projetos"
    lines = [f"Fontes indexadas ({len(sources)} únicas) — {target}:"]
    for pid in sorted(by_project):
        lines.append(f"\n  [{pid}] — {len(by_project[pid])} arquivo(s):")
        for src in sorted(by_project[pid]):
            lines.append(f"    • {src}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# FERRAMENTAS: Configuração
# ═══════════════════════════════════════════════════════════════════════════════

@mcp_tool_with_logging
async def get_server_settings() -> str:
    """Retorna relatório completo das configurações ativas (fábrica + overrides do usuário)."""
    settings = rag.config.get_all()
    user_changes = rag.config.user_prefs
    report = {
        "store_type": rag.store_type,
        "ollama": {
            "base_url": rag.ollama.base_url,
            "embedding_model": rag.ollama.embedding_model,
            "rag_model": rag.ollama.rag_model,
            "num_ctx": rag.ollama.num_ctx,
        },
        "active_settings": settings,
        "user_overrides": user_changes,
    }
    return json.dumps(report, indent=4, ensure_ascii=False)


@mcp_tool_with_logging
async def update_indexing_settings(
    ignored_extensions: list = None,
    ignored_dirs: list = None,
    use_gitignore: bool = None,
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> str:
    """Atualiza configurações de indexação. Persiste em data/user_preferences.json.

    Args:
        ignored_extensions: Lista de extensões a ignorar (ex: ['.log', '.tmp']).
                            Sobrescreve a lista atual — inclua tudo que deseja ignorar.
        ignored_dirs: Lista de nomes de diretórios a ignorar.
        use_gitignore: True para respeitar .gitignore dos projetos.
        chunk_size: Tamanho máximo de chunk em caracteres para o splitter.
        chunk_overlap: Overlap entre chunks em caracteres.
    """
    updates = {}
    if ignored_extensions is not None:
        updates["ignored_extensions"] = ignored_extensions
    if ignored_dirs is not None:
        updates["ignored_dirs"] = ignored_dirs
    if use_gitignore is not None:
        updates["use_gitignore"] = use_gitignore
    if chunk_size is not None:
        updates["chunk_size"] = chunk_size
    if chunk_overlap is not None:
        updates["chunk_overlap"] = chunk_overlap
    if not updates:
        return "Nenhuma configuração foi alterada."
    rag.config.update("indexing", updates)
    return f"Configurações de indexação atualizadas: {list(updates.keys())}"


@mcp_tool_with_logging
async def update_vision_settings(
    auto_index_images: bool = None,
    auto_index_folders: list = None,
) -> str:
    """Configura comportamento da indexação de imagens (Vision multimodal)."""
    updates = {}
    if auto_index_images is not None:
        updates["auto_index_images"] = auto_index_images
    if auto_index_folders is not None:
        updates["auto_index_folders"] = auto_index_folders
    if not updates:
        return "Nenhuma configuração de visão foi alterada."
    rag.config.update("vision", updates)
    return f"Configurações de visão atualizadas: {list(updates.keys())}"


@mcp_tool_with_logging
async def reset_server_settings() -> str:
    """Restaura todas as configurações para os padrões de fábrica."""
    rag.config.reset_to_defaults()
    return "Servidor restaurado para padrões de fábrica. user_preferences.json removido."


# ═══════════════════════════════════════════════════════════════════════════════
# FERRAMENTAS: Sistema / Hardware
# ═══════════════════════════════════════════════════════════════════════════════

@mcp_tool_with_logging
async def check_ollama_status() -> str:
    """Verifica conexão com Ollama e disponibilidade dos modelos configurados."""
    status = await asyncio.to_thread(rag.ollama.check_connection)
    if not status["connected"]:
        return (
            f"✗ Ollama DESCONECTADO ({rag.ollama.base_url})\n"
            f"  Erro: {status.get('error', 'desconhecido')}\n"
            f"  Solução: Inicie o Ollama e verifique a porta."
        )
    embed_ok = "✓" if status["embedding_model_ok"] else "✗ NÃO ENCONTRADO"
    rag_ok = "✓" if status["rag_model_ok"] else "✗ NÃO ENCONTRADO"
    return (
        f"✓ Ollama CONECTADO ({rag.ollama.base_url})\n"
        f"  Embedding ({rag.ollama.embedding_model}): {embed_ok}\n"
        f"  RAG/Vision ({rag.ollama.rag_model}): {rag_ok}\n"
        f"  Modelos disponíveis: {', '.join(status.get('available_models', []))}"
    )


@mcp_tool_with_logging
async def get_gpu_status() -> str:
    """Verifica uso atual de VRAM da GPU (apenas NVIDIA via nvidia-smi)."""
    return rag.ollama.get_gpu_usage()


@mcp_tool_with_logging
async def unload_vram() -> str:
    """Descarrega os modelos Ollama da VRAM imediatamente (Ejecao de Emergencia)."""
    success = rag.ollama.unload_models()
    return "Modelos descarregados. VRAM liberada." if success else "Falha ao descarregar modelos."


@mcp_tool_with_logging
async def clear_knowledge_base(project_id: str = None) -> str:
    """Limpa a base de dados vetorial.

    Args:
        project_id: Se informado, limpa apenas este projeto. Caso contrario, limpa tudo.
    """
    result = await asyncio.to_thread(rag.clear_database, project_id)
    return result


# --- Entry point --------------------------------------------------------------

_heartbeat_stop = threading.Event()
_heartbeat_thread: threading.Thread | None = None
_exit_called = threading.Event()


def handle_exit():
    """Libera recursos ao encerrar o servidor (atexit + signal handlers)."""
    if _exit_called.is_set():
        return
    _exit_called.set()

    from src.services.lifecycle import drain_model_guard, remove_pid_file
    logger.info("Encerrando MCP Rust Star Knowledge Server...")
    _bus.emit("server.stopped", {})
    drain_model_guard()
    _heartbeat_stop.set()
    if _heartbeat_thread is not None and _heartbeat_thread.is_alive():
        _heartbeat_thread.join(timeout=3.0)
    try:
        payload = _telemetry.snapshot(
            embed_state=_embed_state,
            rag_state=rag.state,
            batch_progress=_batch_progress_cache,
            server_extra=_server_extra,
        )
        _telemetry.flush(payload)
    except Exception:
        pass
    rag.ollama.unload_models()
    remove_pid_file()
    logger.info("Encerrando MCP Rust Star Knowledge Server. Liberando VRAM... OK")


async def _windows_stdin_keepalive():
    """Previne o deadlock do ProactorEventLoop ocioso no Windows com stdin."""
    while True:
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    import atexit
    import signal

    atexit.register(handle_exit)

    def _sig_handler(sig, frame):
        handle_exit()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sig_handler)
    try:
        signal.signal(signal.SIGINT, _sig_handler)
    except (OSError, ValueError):
        pass

    from src.services.lifecycle import write_pid_file
    write_pid_file()

    logger.info("=== MCP RUST STAR KNOWLEDGE SERVER INICIADO ===")
    _bus.emit("server.started", {})

    _heartbeat_thread = threading.Thread(
        target=_telemetry.heartbeat_loop,
        args=(_heartbeat_stop,),
        daemon=True
    )
    _heartbeat_thread.start()

    _windows_task = None
    if sys.platform == "win32":
        try:
            _windows_task = asyncio.get_event_loop().create_task(_windows_stdin_keepalive())
        except RuntimeError:
            pass

    mcp.run(transport=_TRANSPORT)
