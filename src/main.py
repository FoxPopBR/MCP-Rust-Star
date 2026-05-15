import asyncio
import os
import sys
import json
from functools import wraps
from contextlib import redirect_stdout

from mcp.server.fastmcp import FastMCP
from src.services.rag_service import RAGService
from tools.logger import logger

# Inicializa o servidor MCP
mcp = FastMCP("Rust Star Knowledge Server")
rag = RAGService()

# Garante que os diretórios base existam
os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)

PROJECTS_FILE = "data/projects.json"

def load_projects():
    if os.path.exists(PROJECTS_FILE):
        try:
            with open(PROJECTS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao carregar projetos: {str(e)}")
    return {}

def save_project(project_id, path):
    projects = load_projects()
    projects[project_id] = path
    with open(PROJECTS_FILE, "w") as f:
        json.dump(projects, f, indent=4)

def get_project_for_path(file_path: str) -> str:
    """Identifica o project_id com base no caminho do arquivo (Normalizado para Windows)."""
    projects = load_projects()
    file_path_norm = os.path.normpath(os.path.abspath(file_path)).lower()
    sorted_projects = sorted(projects.items(), key=lambda x: len(x[1]), reverse=True)
    for project_id, project_root in sorted_projects:
        root_norm = os.path.normpath(os.path.abspath(project_root)).lower()
        if file_path_norm.startswith(root_norm):
            return project_id
    return None

def mcp_tool_with_logging(func):
    @mcp.tool()
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Redireciona stdout para stderr APENAS durante a execução da ferramenta
        # Isso evita que prints de bibliotecas quebrem o protocolo JSON-RPC
        with redirect_stdout(sys.stderr):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error_with_traceback(e, func.__name__)
                return f"Erro na ferramenta {func.__name__}: {str(e)}"
    return wrapper

@mcp_tool_with_logging
async def register_project(project_id: str, path: str) -> str:
    """Registra um novo projeto e valida seu caminho no sistema."""
    if not os.path.exists(path):
        return f"Erro: O caminho '{path}' não existe."
    if not os.path.isdir(path):
        return f"Erro: O caminho '{path}' não é um diretório."
    save_project(project_id, path)
    logger.info(f"Projeto '{project_id}' registrado: {path}")
    return f"Projeto '{project_id}' registrado com sucesso."

@mcp_tool_with_logging
async def list_projects() -> str:
    """Lista todos os projetos registrados."""
    projects = load_projects()
    if not projects: return "Nenhum projeto registrado."
    return "Projetos registrados:\n" + "\n".join([f"- {p}: {path}" for p, path in projects.items()])

@mcp_tool_with_logging
async def index_file(path: str) -> str:
    """Indexa um arquivo (texto ou PDF) detectando automaticamente o projeto pelo caminho."""
    if not os.path.exists(path): return f"Erro: Arquivo '{path}' não encontrado."
    project_id = get_project_for_path(path)
    if not project_id: return f"Erro: Arquivo não pertence a nenhum projeto registrado."
    
    result = rag.index_file_by_path(path, project_id)
    return f"Sucesso: {result} (Projeto: {project_id})"

@mcp_tool_with_logging
async def get_server_settings() -> str:
    """Retorna um relatório detalhado das configurações atuais (Fábrica vs Usuário)."""
    settings = rag.config.get_all()
    user_changes = rag.config.user_prefs
    
    report = {
        "active_settings": settings,
        "user_overrides": user_changes,
        "mode": "Industrial v1.1"
    }
    return json.dumps(report, indent=4)

@mcp_tool_with_logging
async def update_indexing_settings(
    ignored_extensions: list = None,
    use_gitignore: bool = None,
    chunk_size: int = None
) -> str:
    """Atualiza as configurações de indexação. Salva permanentemente em data/user_preferences.json."""
    updates = {}
    if ignored_extensions is not None: updates["ignored_extensions"] = ignored_extensions
    if use_gitignore is not None: updates["use_gitignore"] = use_gitignore
    if chunk_size is not None: updates["chunk_size"] = chunk_size
    
    rag.config.update("indexing", updates)
    return "Configurações de indexação atualizadas com sucesso."

@mcp_tool_with_logging
async def update_vision_settings(
    auto_index_images: bool = None,
    auto_index_folders: list = None
) -> str:
    """Configura o comportamento da visão multimodal automática."""
    updates = {}
    if auto_index_images is not None: updates["auto_index_images"] = auto_index_images
    if auto_index_folders is not None: updates["auto_index_folders"] = auto_index_folders
    
    rag.config.update("vision", updates)
    return "Configurações de visão multimodal atualizadas."

@mcp_tool_with_logging
async def reset_server_settings() -> str:
    """Deleta todas as personalizações do usuário e restaura os padrões de fábrica."""
    rag.config.reset_to_defaults()
    return "Servidor restaurado para os padrões de fábrica originais."

@mcp_tool_with_logging
async def index_directory(path: str, extension: str = None) -> str:
    """Indexa um diretório completo respeitando a hierarquia de filtros v1.1."""
    abs_path = os.path.abspath(path)
    if not os.path.isdir(abs_path): return f"Erro: Diretório inválido."
    
    project_id = get_project_for_path(abs_path)
    if not project_id: return f"Erro: Diretório não pertence a nenhum projeto registrado."
    
    projects = load_projects()
    project_root = projects.get(project_id)
    
    settings = rag.config.get_all()
    vision_cfg = settings["vision"]
    image_exts = vision_cfg["allowed_image_extensions"]

    count = 0
    skipped = 0
    vision_count = 0

    for root, _, files in os.walk(abs_path):
        for file in files:
            file_path = os.path.join(root, file)
            
            # 1. Filtros de Elite (Extensões + Gitignore)
            if rag.config.is_ignored(file_path, project_root):
                skipped += 1
                continue
            
            # 2. Filtro de Extensão Manual (se informado)
            if extension and not file.lower().endswith(extension.lower()):
                continue

            try:
                file_ext = os.path.splitext(file)[1].lower()
                # 3. Lógica Multimodal v1.1
                if file_ext in image_exts:
                    is_auto_folder = any(os.path.abspath(f) in os.path.abspath(file_path) for f in vision_cfg["auto_index_folders"])
                    if vision_cfg["auto_index_images"] or is_auto_folder:
                        rag.index_image(file_path, project_id)
                        vision_count += 1
                        count += 1
                    continue
                
                # 4. Indexação Normal (Texto/PDF)
                rag.index_file_by_path(file_path, project_id, session_active=True)
                count += 1
            except Exception as e:
                logger.warning(f"Falha ao indexar {file_path}: {str(e)}")
    
    if count > 0:
        rag.ollama.unload_models()
                
    return f"Concluído: {count} indexados ({vision_count} via Vision), {skipped} ignorados por filtros. Projeto: '{project_id}'."

@mcp_tool_with_logging
async def index_image(path: str) -> str:
    """Dispara manualmente a visão multimodal para descrever e indexar uma imagem (PNG/JPG)."""
    if not os.path.exists(path): return f"Erro: Imagem '{path}' não encontrada."
    project_id = get_project_for_path(path)
    if not project_id: return f"Erro: Imagem não pertence a nenhum projeto registrado."
    
    result = rag.index_image(path, project_id)
    return f"Visão Concluída: {result} (Projeto: {project_id})"

@mcp_tool_with_logging
async def clear_knowledge_base(project_id: str = None) -> str:
    """Limpa a base de dados vetorial. Se project_id for informado, limpa apenas esse projeto."""
    result = rag.clear_database(project_id)
    return result

@mcp_tool_with_logging
async def ask_knowledge_base(question: str, project_id: str = None) -> str:
    """Consulta a base de conhecimento com RAG isolado por projeto."""
    result = rag.search_and_generate(question, project_id)
    target = project_id if project_id else "TODOS"
    response = f"RESPOSTA ({target}):\n{result['answer']}\n\n"
    if result['context_used']:
        response += "CONTEXTO ENCONTRADO:\n" + "\n".join([f"- {c[:100]}..." for c in result['context_used']])
    else:
        response += "(Nenhum contexto específico encontrado)"
    return response

@mcp_tool_with_logging
async def check_ollama_status() -> str:
    """Verifica conexão com Ollama e disponibilidade dos modelos."""
    status = rag.ollama.check_connection()
    if status['connected']:
        return f"Ollama Conectado! (Embed: {'OK' if status['embedding_model_ok'] else 'Falha'}, RAG: {'OK' if status['rag_model_ok'] else 'Falha'})"
    return f"Ollama Desconectado: {status.get('error', 'Erro desconhecido')}"

@mcp_tool_with_logging
async def get_gpu_status() -> str:
    """Verifica o uso atual da memória VRAM da GPU (Apenas NVIDIA)."""
    return rag.ollama.get_gpu_usage()

@mcp_tool_with_logging
async def unload_vram() -> str:
    """Descarrega os modelos da memória de vídeo (VRAM) imediatamente."""
    success = rag.ollama.unload_models()
    return "Modelos descarregados com sucesso. VRAM liberada." if success else "Falha ao descarregar modelos."

def handle_exit():
    """Garante que os recursos sejam liberados ao fechar o servidor."""
    logger.info("Encerrando servidor MCP... Liberando VRAM.")
    rag.ollama.unload_models()

if __name__ == "__main__":
    import signal
    import atexit
    
    # Registra a limpeza para encerramento normal e via sinais (CTRL+C)
    atexit.register(handle_exit)
    
    logger.info("=== SERVIDOR MCP RUST STAR INICIADO ===")
    mcp.run()
