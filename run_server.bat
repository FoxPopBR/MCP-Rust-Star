@echo off
setlocal enabledelayedexpansion
title MCP Rust Star - Servidor de Conhecimento

:: --- CONFIGURAÇÕES ---
set "PROJECT_ROOT=%~dp0"
set "PYTHON_EXE=%PROJECT_ROOT%.venv\Scripts\python.exe"
set "OLLAMA_PORT=11434"
set "PYTHONPATH=%PROJECT_ROOT%"

echo ==========================================================
echo    MCP RUST STAR - INICIALIZADOR DE ALTA FIDELIDADE
echo ==========================================================

:: 1. SANEAMENTO: Encerra instâncias órfãs do servidor
echo [1/4] Limpando processos antigos...
for /f "tokens=2 delims=," %%a in ('wmic process where "commandline like '%%src.main%%' and name='python.exe'" get processid /format:csv 2^>nul') do (
    set "pid=%%a"
    if not "!pid!"=="" if not "!pid!"=="ProcessId" (
        echo [!] Finalizando instancia anterior (PID: !pid!^)...
        taskkill /f /pid !pid! >nul 2>&1
    )
)

:: 2. VERIFICAÇÃO: Saúde do Ambiente (Ollama)
echo [2/4] Verificando dependencias externas...
netstat -ano | findstr ":%OLLAMA_PORT%" >nul
if %ERRORLEVEL% neq 0 (
    echo [ERRO] O servico Ollama nao foi detectado na porta %OLLAMA_PORT%.
    echo [!] Por favor, inicie o Ollama antes de rodar o servidor MCP.
    pause
    exit /b 1
)
echo [OK] Ollama detectado e operacional.

:: 3. VERIFICAÇÃO: Dependências Python
echo [3/4] Validando bibliotecas Python...
"%PYTHON_EXE%" -c "import langchain_text_splitters" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [AVISO] Bibliotecas faltando. Instalando requerimentos...
    "%PYTHON_EXE%" -m pip install -r "%PROJECT_ROOT%requirements.txt"
) else (
    echo [OK] Bibliotecas Python validadas.
)

:: 4. EXECUÇÃO: Inicia o servidor
echo [4/4] Iniciando Servidor MCP (Modo STDIO)...
echo ----------------------------------------------------------
echo [INFO] Logs estao sendo gravados em: %PROJECT_ROOT%logs\mcp_error.log
echo [INFO] Pressione CTRL+C para encerrar.
echo ----------------------------------------------------------

"%PYTHON_EXE%" -u -m src.main

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ALERTA] O servidor parou inesperadamente (Codigo: %ERRORLEVEL%).
    echo [TIP] Verifique os logs em %PROJECT_ROOT%logs\mcp_error.log para detalhes.
)

pause
