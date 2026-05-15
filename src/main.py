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
from collections import Counter
from functools import wraps
from contextlib import redirect_stdout

from mcp.server.fastmcp import FastMCP
from src.services.rag_service import RAGService
from tools.logger import logger

# ─── Inicialização do servidor ─────────────────────────────────────────────────

mcp = FastMCP("Rust Star Knowledge Server")
rag = RAGService()

os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)

PROJECTS_FILE = "data/projects.json"
BATCH_PROGRESS_FILE = "data/batch_progress.json"


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
    """Persiste o progresso atual da sessão batch."""
    try:
        with open(BATCH_PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Falha ao salvar progresso batch: {e}")


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
    """
    Registra a função como ferramenta MCP e:
    - Loga o início e fim da execução (Heartbeat).
    - Captura exceções, loga com traceback e retorna mensagem de erro amigável.
    """
    @mcp.tool()
    @wraps(func)
    async def wrapper(*args, **kwargs):
        tool_name = func.__name__
        logger.info(f"[TOOL START] Executando '{tool_name}'...")
        start_time = datetime.datetime.now()
        try:
            result = await func(*args, **kwargs)
            duration = (datetime.datetime.now() - start_time).total_seconds()
            logger.info(f"[TOOL END] '{tool_name}' concluída em {duration:.2f}s")
            return result
        except Exception as e:
            duration = (datetime.datetime.now() - start_time).total_seconds()
            logger.error(f"[TOOL ERROR] Falha em '{tool_name}' após {duration:.2f}s")
            logger.error_with_traceback(e, tool_name)
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


# ═══════════════════════════════════════════════════════════════════════════════
# CORE DE INDEXAÇÃO (com atualização de estado + retry)
# ═══════════════════════════════════════════════════════════════════════════════

def _walk_and_index_sync(
    project_id: str,
    abs_path: str,
    project_root: str,
    extension: str = None,
    max_retries: int = 2,
) -> dict:
    """Walk-and-index rodando 100% em Thread separada."""
    settings = rag.config.get_all()
    vision_cfg = settings["vision"]
    image_exts = set(vision_cfg.get("allowed_image_extensions", []))

    count = skipped = cached = vision_count = errors = 0
    retry_queue = []  # arquivos que falharam na primeira tentativa

    _embed_state["current_project"] = project_id
    _embed_log(f"Início: {project_id} | {abs_path}")

    # ── PRE-SCAN RÁPIDO PARA ESTATÍSTICAS ─────────────────────────────────────
    total_eligible = 0
    _embed_log("Executando pré-scan de arquivos elegíveis...")
    for root, dirs, files in os.walk(abs_path):
        if not _embed_state["running"]: break
        dirs[:] = [d for d in dirs if not rag.config.is_ignored(os.path.join(root, d), project_root)]
        for file in files:
            file_path = os.path.join(root, file)
            if not rag.config.is_ignored(file_path, project_root):
                if extension and not file.lower().endswith(extension.lower()): continue
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in image_exts:
                    file_abs = os.path.abspath(file_path)
                    is_auto_folder = any(
                        file_abs.startswith(os.path.abspath(f) + os.sep)
                        for f in vision_cfg.get("auto_index_folders", [])
                    )
                    if not (vision_cfg.get("auto_index_images", False) or is_auto_folder):
                        continue
                total_eligible += 1

    _embed_state["total_expected"] = total_eligible
    _embed_log(f"Pré-scan concluído: {total_eligible} arquivos elegíveis.")

    # ── INDEXAÇÃO REAL ────────────────────────────────────────────────────────
    for root, dirs, files in os.walk(abs_path):
        # Verifica cancelamento antes de cada diretório
        if not _embed_state["running"]:
            _embed_log(f"Cancelado em: {project_id}")
            break

        # Poda diretórios ignorados in-place
        dirs[:] = [
            d for d in dirs
            if not rag.config.is_ignored(os.path.join(root, d), project_root)
        ]

        for file in files:
            if not _embed_state["running"]:
                break

            file_path = os.path.join(root, file)
            _embed_state["current_file"] = os.path.relpath(file_path, project_root)

            if rag.config.is_ignored(file_path, project_root):
                skipped += 1
                rag.update_state(stats_inc={"skipped": 1})
                continue

            if extension and not file.lower().endswith(extension.lower()):
                continue

            try:
                file_ext = os.path.splitext(file)[1].lower()

                # Imagens: só se Vision estiver ativo
                if file_ext in image_exts:
                    file_abs = os.path.abspath(file_path)
                    is_auto_folder = any(
                        file_abs.startswith(os.path.abspath(f) + os.sep)
                        for f in vision_cfg.get("auto_index_folders", [])
                    )
                    if vision_cfg.get("auto_index_images", False) or is_auto_folder:
                        rag.index_image(file_path, project_id)
                        vision_count += 1
                        count += 1
                        _embed_state["stats"]["new"] += 1
                        _embed_state["stats_by_ext"][file_ext] = _embed_state["stats_by_ext"].get(file_ext, 0) + 1
                    else:
                        skipped += 1
                        rag.update_state(stats_inc={"skipped": 1})
                    continue

                result = rag.index_file_by_path(file_path, project_id, session_active=True)
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

    # ── RETRY AUTOMÁTICO ──────────────────────────────────────────────────────
    if retry_queue and max_retries > 0:
        _embed_log(f"Retry: {len(retry_queue)} arquivo(s) com falha em '{project_id}'")
        retry_success = 0
        still_failed = []

        for item in retry_queue:
            try:
                result = rag.index_file_by_path(item["file"], project_id, session_active=True)
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
    _embed_state["current_project"] = None

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
                "project_id": pid,
                "project_root": projects[pid],
                "force": force,
            })

    _embed_state["total_projects"] = len(_embed_state["queue"])
    _embed_log(
        f"Worker iniciado | {_embed_state['total_projects']} projeto(s) na fila"
        + (f" | Retomando: {sorted(completed_prev)}" if completed_prev else "")
    )

    try:
        while _embed_state["queue"] and _embed_state["running"]:
            item = _embed_state["queue"].pop(0)
            project_id = item["project_id"]
            project_root = item["project_root"]
            item_force = item.get("force", force)

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
                _embed_log(f"DEBUG: Iniciando _walk_and_index_sync para {project_id}")
                stats = await asyncio.wait_for(
                    asyncio.to_thread(_walk_and_index_sync, project_id, project_root, project_root),
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

    finally:
        await asyncio.to_thread(rag.ollama.unload_models)
        _embed_state["running"] = False
        _embed_state["current_project"] = None
        _embed_state["current_file"] = None
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

@mcp_tool_with_logging
async def index_file(path: str) -> str:
    """Indexa um arquivo individual (.rs, .cpp, .h, .lua, .py, .md, .pdf, etc.).
    Detecta o projeto automaticamente pelo caminho."""
    if not os.path.exists(path):
        return f"Erro: Arquivo '{path}' não encontrado."
    project_id = get_project_for_path(path)
    if not project_id:
        return (
            f"Erro: '{path}' não pertence a nenhum projeto registrado. "
            f"Use register_project primeiro."
        )
    result = await asyncio.to_thread(rag.index_file_by_path, path, project_id)
    return f"{result} | Projeto: {project_id}"


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

    _embed_state["running"] = True
    try:
        stats = await asyncio.to_thread(_walk_and_index_sync, project_id, abs_path, project_root, extension)
    finally:
        _embed_state["running"] = False

    if stats["new"] > 0 or stats["vision"] > 0:
        await asyncio.to_thread(rag.ollama.unload_models)

    return (
        f"Indexação concluída | Projeto: '{project_id}'\n"
        f"  ✓ Novos:     {stats['new']} arquivo(s) ({stats['vision']} via Vision)\n"
        f"  ⊙ Cache:     {stats['cached']} arquivo(s) inalterados (ignorados)\n"
        f"  ○ Ignorados: {stats['skipped']} arquivo(s) por filtros\n"
        f"  ✗ Erros:     {stats['errors']} arquivo(s)"
    )


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
async def index_image(path: str) -> str:
    """Indexa uma imagem manualmente via Vision (PNG/JPG).
    Detecta o projeto automaticamente pelo caminho."""
    if not os.path.exists(path):
        return f"Erro: Imagem '{path}' não encontrada."
    project_id = get_project_for_path(path)
    if not project_id:
        return f"Erro: '{path}' não pertence a nenhum projeto registrado."
    result = rag.index_image(path, project_id)
    return f"Visão concluída: {result} | Projeto: {project_id}"


# ═══════════════════════════════════════════════════════════════════════════════
# FERRAMENTAS: Análise Visual de Screenshots
# ═══════════════════════════════════════════════════════════════════════════════

@mcp_tool_with_logging
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
            rag.index_text(enriched_text, project_id, source=abs_path)
            kb_status = f"\n\n[✓ Análise salva na base de conhecimento | Projeto: {project_id}]"
        else:
            kb_status = "\n\n[⚠ Nenhum projeto registrado. Análise não salva na KB.]"

    return f"=== ANÁLISE DO SCREENSHOT: {os.path.basename(path)} ===\n\n{description}{kb_status}"


# ═══════════════════════════════════════════════════════════════════════════════
# FERRAMENTAS: Busca RAG
# ═══════════════════════════════════════════════════════════════════════════════

@mcp_tool_with_logging
async def ask_knowledge_base(question: str, project_id: str = None) -> str:
    """Consulta a base de conhecimento com RAG. Retorna resposta com citação de fontes.

    Args:
        question: Sua pergunta técnica sobre código, arquitetura, etc.
        project_id: Opcional. Filtra por projeto (ex: 'Rust Star', 'FoxOT', 'FoxClient').
                    Se omitido, busca em todos os projetos.
    """
    result = await asyncio.to_thread(rag.search_and_generate, question, project_id)
    target = project_id if project_id else "TODOS OS PROJETOS"

    response = f"=== RESPOSTA [{target}] ===\n\n{result['answer']}\n\n"

    if result.get("sources"):
        response += "=== FONTES CONSULTADAS ===\n"
        seen = set()
        for meta in result["sources"]:
            if meta:
                src = meta.get("source", "desconhecido")
                proj = meta.get("project_id", "?")
                key = (proj, src)
                if key not in seen:
                    seen.add(key)
                    response += f"  • [{proj}] {os.path.basename(src)}\n"
    else:
        response += "(Nenhum contexto específico encontrado na base de conhecimento)"

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
    return await asyncio.to_thread(rag.ollama.get_gpu_usage)


@mcp_tool_with_logging
async def unload_vram() -> str:
    """Descarrega os modelos Ollama da VRAM imediatamente (Ejeção de Emergência)."""
    success = await asyncio.to_thread(rag.ollama.unload_models)
    return "✓ Modelos descarregados. VRAM liberada." if success else "✗ Falha ao descarregar modelos."


@mcp_tool_with_logging
async def clear_knowledge_base(project_id: str = None) -> str:
    """Limpa a base de dados vetorial.

    Args:
        project_id: Se informado, limpa apenas este projeto. Caso contrário, limpa tudo.
    """
    result = await asyncio.to_thread(rag.clear_database, project_id)
    return result


# ─── Entry point ───────────────────────────────────────────────────────────────

def handle_exit():
    """Libera recursos ao encerrar o servidor."""
    logger.info("Encerrando MCP Rust Star Knowledge Server. Liberando VRAM...")
    rag.ollama.unload_models()


async def _windows_stdin_keepalive():
    """Previne o deadlock do ProactorEventLoop ocioso no Windows com stdin."""
    while True:
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    import atexit
    atexit.register(handle_exit)
    
    # Injeta a task de keepalive no event loop antes do MCP rodar
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    loop.create_task(_windows_stdin_keepalive())
    
    logger.info("=== MCP RUST STAR KNOWLEDGE SERVER INICIADO ===")
    mcp.run()
