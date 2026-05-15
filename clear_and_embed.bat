@echo off
echo.
echo ============================================================
echo   MCP RUST STAR - LIMPAR BANCO E REINDEXAR TUDO
echo ============================================================
echo.

cd /d "C:\Phantasy\MCP Rust Star"

echo [1/3] Limpando banco de dados...
.venv\Scripts\python.exe clear_db.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Falha ao limpar banco. Abortando.
    pause
    exit /b 1
)

echo.
echo [2/3] Escaneando extensoes antes de indexar...
.venv\Scripts\python.exe run_batch_index.py --scan-only
echo.

echo [3/3] Iniciando embed de todos os projetos...
echo    Projetos: MCP Rust Star, Rust Star, FoxOT, FoxClient
echo    Isso pode levar horas. Deixe rodando.
echo.
.venv\Scripts\python.exe run_batch_index.py --force

echo.
echo ============================================================
echo   CONCLUIDO
echo ============================================================
pause
