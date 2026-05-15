"""
Script para limpar TODOS os dados do banco vetorial (Postgres ou ChromaDB).
Executa antes de re-indexar tudo do zero.

USO:
    cd "C:\Phantasy\MCP Rust Star"
    .venv\Scripts\python.exe clear_db.py
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.services.rag_service import RAGService
from tools.logger import logger

# Desacopla handler de log para não colidir com servidor MCP
import logging
for h in logging.root.handlers[:]:
    if hasattr(h, 'baseFilename') and 'mcp_error' in h.baseFilename:
        try: h.close(); logging.root.removeHandler(h)
        except Exception: pass

PROJECTS_FILE = "data/projects.json"
BATCH_PROGRESS_FILE = "data/batch_progress.json"

def main():
    print("\n" + "="*60)
    print("  MCP RUST STAR — LIMPEZA TOTAL DO BANCO")
    print("="*60)

    rag = RAGService()
    print(f"\n[INFO] Backend: {rag.store_type}")

    projects = {}
    if os.path.exists(PROJECTS_FILE):
        with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
            projects = json.load(f)

    print(f"[INFO] Projetos registrados: {list(projects.keys())}\n")

    # Limpa cada projeto individualmente
    for pid in projects:
        try:
            result = rag.clear_database(pid)
            print(f"[OK] {pid}: {result}")
        except Exception as e:
            print(f"[ERRO] {pid}: {e}")

    # Limpeza total como fallback garantido
    try:
        result = rag.clear_database(None)
        print(f"\n[OK] Limpeza total: {result}")
    except Exception as e:
        print(f"[AVISO] Limpeza total: {e}")

    # Remove progresso antigo
    if os.path.exists(BATCH_PROGRESS_FILE):
        os.remove(BATCH_PROGRESS_FILE)
        print("[OK] batch_progress.json removido")

    print("\n" + "="*60)
    print("  BANCO LIMPO. Execute run_batch_index.py para re-indexar.")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
