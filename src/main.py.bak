"""
MCP Rust Star Knowledge Server
Servidor de base de conhecimento RAG local para os projetos Rust Star, FoxOT e FoxClient.

Ferramentas disponíveis:
  Gestão de Projetos : register_project, list_projects
  Indexação          : index_file, index_directory, index_image,
                       batch_index_projects
  Busca RAG          : ask_knowledge_base
  Análise Visual     : analyze_screenshot
  Fontes Indexadas   : list_indexed_sources
  Sistema            : get_server_settings, update_indexing_settings,
                       update_vision_settings, reset_server_settings,
                       check_ollama_status, get_gpu_status, unload_vram,
                       clear_knowledge_base
"""

import asyncio
import os
import sys
import json
from functools import wraps
from contextlib import redirect_stdout

from mcp.server.fastmcp import FastMCP
from src.services.rag_service import RAGService
from tools.logger import logger

# ─── Inicialização do servidor ────────────────────────────────────────────────

mcp = FastMCP("Rust Star Knowledge Server")
rag = RAGService()

os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)

PROJECTS_FILE = "data/projects.json"
BATCH_PROGRESS_FILE = "data/batch_progress.json"


# ─── Helpers de projetos ──────────────────────────────────────────────────────

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
    # Ordena por comprimento de caminho decrescente (mais específico vence)
    for project_id, project_root in sorted(projects.items(), key=lambda x: len(x[1]), reverse=True):
        root_norm = os.path.normpath(os.path.abspath(project_root)).lower()
        # Usa startswith com separador para evitar false-positive (ex: /foo vs /foobar)
        if file_norm == root_norm or file_norm.startswith(root_norm + os.sep):
            return project_id
    return None


# ─── Decorator de logging para ferramentas MCP ───────────────────────────────

def mcp_tool_with_logging(func):
    """
    Registra a função como ferramenta MCP e:
    - Redireciona stdout → stderr durante execução (protege o protocolo JSON-RPC)
    - Captura exceções, loga com traceback e retorna mensagem de erro amigável
    """
    @mcp.tool()
    @wraps(func)
    async def wrapper(*args, **kwargs):
        with redirect_stdout(sys.stderr):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error_with_traceback(e, func.__name__)
                return f"Erro na ferramenta '{func.__name__}': {str(e)}"
    return wrapper


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
    result = rag.index_file_by_path(path, project_id)
    return f"{result} | Projeto: {project_id}"


async def _walk_and_index(
    project_id: str,
    abs_path: str,
    project_root: str,
    extension: str = None,
) -> dict:
    """Core de indexação de diretório. Retorna dict de estatísticas.
    Reutilizado por index_directory e batch_index_projects.
    """
    settings = rag.config.get_all()
    vision_cfg = settings["vision"]
    image_exts = set(vision_cfg.get("allowed_image_extensions", []))

    count = skipped = cached = vision_count = errors = 0

    logger.info(f"Indexando: {abs_path} | Projeto: {project_id}")

    for root, dirs, files in os.walk(abs_path):
        # Poda diretórios ignorados in-place para evitar descida desnecessária
        dirs[:] = [
            d for d in dirs
            if not rag.config.is_ignored(os.path.join(root, d), project_root)
        ]

        for file in files:
            file_path = os.path.join(root, file)

            if rag.config.is_ignored(file_path, project_root):
                skipped += 1
                continue

            if extension and not file.lower().endswith(extension.lower()):
                continue

            try:
                file_ext = os.path.splitext(file)[1].lower()

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
                    else:
                        skipped += 1
                    continue

                result = rag.index_file_by_path(file_path, project_id, session_active=True)
                if "Cache Hit" in result:
                    cached += 1
                else:
                    count += 1

            except Exception as e:
                logger.warning(f"Falha ao indexar {file_path}: {str(e)}")
                errors += 1

    return {
        "new": count,
        "cached": cached,
        "skipped": skipped,
        "vision": vision_count,
        "errors": errors,
    }


@mcp_tool_with_logging
async def index_directory(path: str, extension: str = None) -> str:
    """Indexa um diretório completo respeitando filtros de extensão e .gitignore.

    Args:
        path: Diretório a indexar (deve pertencer a um projeto registrado).
        extension: Opcional. Filtra por extensão (ex: '.rs', '.cpp').
    """
    status = rag.ollama.check_connection()
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

    stats = await _walk_and_index(project_id, abs_path, project_root, extension)

    if stats["new"] > 0 or stats["vision"] > 0:
        rag.ollama.unload_models()

    return (
        f"Indexação concluída | Projeto: '{project_id}'\n"
        f"  ✓ Novos:     {stats['new']} arquivo(s) ({stats['vision']} via Vision)\n"
        f"  ⊙ Cache:     {stats['cached']} arquivo(s) inalterados (ignorados)\n"
        f"  ○ Ignorados: {stats['skipped']} arquivo(s) por filtros\n"
        f"  ✗ Erros:     {stats['errors']} arquivo(s)"
    )


@mcp_tool_with_logging
async def batch_index_projects(project_ids: list = None, force: bool = False) -> str:
    """Indexa múltiplos projetos sequencialmente com progresso persistido.

    Salva progresso em data/batch_progress.json após cada projeto concluído.
    Se interrompido (crash, Ctrl+C, reinício), retoma automaticamente do ponto
    onde parou — projetos já concluídos são pulados.
    O cache MD5 garante que arquivos já indexados nunca sejam reprocessados,
    mesmo dentro de um projeto parcialmente indexado.

    Args:
        project_ids: Lista de IDs de projeto a indexar em ordem.
                     Se None, usa todos os projetos registrados.
                     Ex: ["MCP Rust Star", "Rust Star", "FoxOT", "FoxClient"]
        force: Se True, reprocessa projetos já marcados como concluídos
               no progresso salvo (útil para re-indexar após mudanças).
    """
    # ── PRE-FLIGHT ────────────────────────────────────────────────────────────
    status = rag.ollama.check_connection()
    if not status["connected"]:
        return (
            f"Erro: Ollama não está disponível. "
            f"Inicie o Ollama antes de indexar. Detalhe: {status.get('error', '')}"
        )

    projects = load_projects()
    if not projects:
        return "Nenhum projeto registrado. Use register_project primeiro."

    # Resolve lista de projetos
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

    # ── PROGRESSO ANTERIOR ────────────────────────────────────────────────────
    progress = {} if force else load_batch_progress()
    completed = set(progress.get("completed", []))
    results = progress.get("results", {})

    lines = [
        f"╔══ BATCH INDEX: {len(target_ids)} projeto(s) ══╗",
        f"  Projetos: {target_ids}",
        f"  Já concluídos (da sessão anterior): {sorted(completed & set(target_ids))}",
        "",
    ]
    logger.info(f"[BATCH] Iniciando: {target_ids} | Concluídos: {sorted(completed)}")

    # ── LOOP PRINCIPAL ────────────────────────────────────────────────────────
    for project_id in target_ids:
        # Pula projetos já concluídos (retomada automática)
        if project_id in completed and not force:
            prev = results.get(project_id, {})
            lines.append(
                f"✓ {project_id}: concluído anteriormente "
                f"({prev.get('new', '?')} novos, {prev.get('cached', '?')} cache) "
                f"— pulando"
            )
            continue

        project_root = projects.get(project_id)
        if not project_root or not os.path.isdir(project_root):
            msg = f"Caminho inválido ou inacessível: '{project_root}'"
            lines.append(f"✗ {project_id}: {msg}")
            results[project_id] = {"status": "erro", "message": msg}
            save_batch_progress({"completed": sorted(completed), "results": results})
            logger.warning(f"[BATCH] Pulando {project_id}: {msg}")
            continue

        lines.append(f"⟳ {project_id}: iniciando ({project_root})...")
        logger.info(f"[BATCH] Projeto: {project_id} | Root: {project_root}")

        try:
            stats = await _walk_and_index(project_id, project_root, project_root)

            # Descarrega VRAM entre projetos para não acumular
            rag.ollama.unload_models()

            summary = (
                f"✓ {project_id}: "
                f"{stats['new']} novos | "
                f"{stats['cached']} cache | "
                f"{stats['skipped']} ignorados"
                + (f" | {stats['errors']} ERROS" if stats["errors"] else "")
            )
            lines[-1] = summary  # Substitui o "⟳ iniciando..."

            completed.add(project_id)
            results[project_id] = {"status": "ok", **stats}
            save_batch_progress({"completed": sorted(completed), "results": results})
            logger.info(f"[BATCH] Concluído: {project_id} | Stats: {stats}")

        except Exception as e:
            msg = str(e)
            lines[-1] = f"✗ {project_id}: FALHA — {msg}"
            results[project_id] = {"status": "erro", "message": msg}
            save_batch_progress({"completed": sorted(completed), "results": results})
            logger.error(f"[BATCH] Falha em {project_id}: {msg}")
            # Continua para o próximo projeto

    # ── RELATÓRIO FINAL ───────────────────────────────────────────────────────
    rag.ollama.unload_models()

    pending = [p for p in target_ids if p not in completed]
    lines += [
        "",
        f"╠══ RESUMO ══╣",
        f"  Concluídos: {len(completed & set(target_ids))}/{len(target_ids)}",
    ]

    if pending:
        lines.append(
            f"  Pendentes:  {pending}\n"
            f"  → Execute batch_index_projects() novamente para retomar."
        )
    else:
        lines.append("  Todos os projetos indexados com sucesso! ✓")
        # Limpa arquivo de progresso ao concluir tudo
        try:
            if os.path.exists(BATCH_PROGRESS_FILE):
                os.remove(BATCH_PROGRESS_FILE)
        except Exception:
            pass

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

    # Verificação Ollama
    status = rag.ollama.check_connection()
    if not status["connected"]:
        return f"Erro: Ollama offline. {status.get('error', '')}"
    if not status.get("rag_model_ok"):
        return f"Erro: Modelo RAG '{rag.ollama.rag_model}' não disponível no Ollama."

    logger.info(f"Analisando screenshot: {path}")

    # Injeta hint de contexto no prompt se fornecido
    if context_hint:
        original_prompt = rag.ollama.describe_image
        # Temporariamente substitui o prompt interno com contexto adicional
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

    # Salva na base de conhecimento se solicitado
    kb_status = ""
    if save_to_kb:
        project_id = get_project_for_path(path)
        if not project_id:
            # Tenta salvar no projeto "Rust Star" como default
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
    result = rag.search_and_generate(question, project_id)
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
    sources = rag.list_indexed_sources(project_id)
    if not sources:
        scope = f"projeto '{project_id}'" if project_id else "qualquer projeto"
        return f"Nenhuma fonte indexada encontrada para {scope}."

    # Agrupa por projeto
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
    use_gitignore: bool = None,
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> str:
    """Atualiza configurações de indexação. Persiste em data/user_preferences.json."""
    updates = {}
    if ignored_extensions is not None:
        updates["ignored_extensions"] = ignored_extensions
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
    status = rag.ollama.check_connection()
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
    """Descarrega os modelos Ollama da VRAM imediatamente (Ejeção de Emergência)."""
    success = rag.ollama.unload_models()
    return "✓ Modelos descarregados. VRAM liberada." if success else "✗ Falha ao descarregar modelos."


@mcp_tool_with_logging
async def clear_knowledge_base(project_id: str = None) -> str:
    """Limpa a base de dados vetorial.

    Args:
        project_id: Se informado, limpa apenas este projeto. Caso contrário, limpa tudo.
    """
    result = rag.clear_database(project_id)
    return result


# ─── Entry point ──────────────────────────────────────────────────────────────

def handle_exit():
    """Libera recursos ao encerrar o servidor."""
    logger.info("Encerrando MCP Rust Star Knowledge Server. Liberando VRAM...")
    rag.ollama.unload_models()


if __name__ == "__main__":
    import atexit
    atexit.register(handle_exit)
    logger.info("=== MCP RUST STAR KNOWLEDGE SERVER INICIADO ===")
    mcp.run()
