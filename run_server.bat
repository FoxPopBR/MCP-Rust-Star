@echo off
setlocal enabledelayedexpansion

:: Detecta modo MCP silencioso
set "MCP_MODE=0"
if /I "%~1"=="--mcp" set "MCP_MODE=1"

:: Auto-relança via cmd /k se não for MCP e não tiver sido relançado
if "%MCP_MODE%"=="0" (
    if "%KEEP_OPEN%"=="" (
        set "KEEP_OPEN=1"
        cmd /k "%~f0"
        exit /b
    )
)

:: Encerra janelas antigas de terminal antes de abrir a nova
if "%MCP_MODE%"=="0" (
    taskkill /fi "WINDOWTITLE eq MCP Rust Star - Servidor de Conhecimento*" /f >nul 2>&1
)

title MCP Rust Star - Servidor de Conhecimento

:: ── CONFIGURAÇÕES ────────────────────────────────────────────────────────────
set "PROJECT_ROOT=%~dp0"
set "PYTHON_EXE=%PROJECT_ROOT%.venv\Scripts\python.exe"
set "OLLAMA_PORT=11434"
set "POSTGRES_CONTAINER=mcp-rust-star-db"
set "PYTHONPATH=%PROJECT_ROOT%"
set "MAX_WAIT_SECS=30"
set "MCP_LOG=%PROJECT_ROOT%logs\mcp_error.log"
set "START_LOG=%PROJECT_ROOT%logs\startup.log"

:: Garante pasta de logs
if not exist "%PROJECT_ROOT%logs\" mkdir "%PROJECT_ROOT%logs\"

:: Cabeçalho no log e no console (via STDERR para não corromper MCP)
echo ========================================================== >&2
echo    MCP RUST STAR - INICIALIZADOR                          >&2
echo    %DATE% %TIME%                                          >&2
echo ========================================================== >&2

echo ========================================================== >> "%START_LOG%"
echo    %DATE% %TIME% >> "%START_LOG%"
echo. >&2

:: ── PRE-FLIGHT ────────────────────────────────────────────────────────────────
if not exist "%PYTHON_EXE%" (
    echo [ERRO FATAL] Python venv nao encontrado: >&2
    echo              %PYTHON_EXE% >&2
    echo [ERRO FATAL] Python venv nao encontrado: %PYTHON_EXE% >> "%START_LOG%"
    echo [!] Execute: python -m venv .venv >&2
    echo. >&2
    if "%MCP_MODE%"=="0" pause >nul
    exit /b 1
)

docker --version >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [ERRO FATAL] Comando 'docker' nao encontrado no PATH. >&2
    echo [ERRO FATAL] docker nao encontrado >> "%START_LOG%"
    echo [!] Verifique se o Docker Desktop esta instalado. >&2
    echo. >&2
    if "%MCP_MODE%"=="0" pause >nul
    exit /b 1
)

:: ── PASSO 1: Encerra instâncias órfãs ────────────────────────────────────────
echo [1/5] Verificando instancias ativas do servidor... >&2
echo [1/5] Verificando instancias ativas >> "%START_LOG%"
set "KILLED=0"
for /f %%a in ('powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'src\.main' -and $_.Name -eq 'python.exe' } | Select-Object -ExpandProperty ProcessId" 2^>nul') do (
    set "pid=%%a"
    if not "!pid!"=="" (
        taskkill /f /pid !pid! /t >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            echo    [OK] Instancia anterior encerrada ^(PID: !pid!^) >&2
            echo    [OK] Instancia encerrada PID !pid! >> "%START_LOG%"
            set "KILLED=1"
        ) else (
            echo    [AVISO] Nao foi possivel encerrar PID !pid! >&2
            echo    [AVISO] Falha ao encerrar PID !pid! >> "%START_LOG%"
        )
    )
)
if "%KILLED%"=="0" (
    echo    [OK] Nenhuma instancia anterior encontrada. >&2
) else (
    echo    [OK] Aguardando processos encerrarem... >&2
    timeout /t 2 /nobreak >nul
)

:: ── PASSO 2: Ollama ───────────────────────────────────────────────────────────
echo [2/5] Verificando Ollama (porta %OLLAMA_PORT%)... >&2
echo [2/5] Verificando Ollama >> "%START_LOG%"
netstat -ano | findstr ":%OLLAMA_PORT% " >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [ERRO] Ollama nao detectado na porta %OLLAMA_PORT%. >&2
    echo [ERRO] Ollama nao detectado na porta %OLLAMA_PORT% >> "%START_LOG%"
    echo [!] Inicie o Ollama antes de rodar o servidor MCP. >&2
    echo. >&2
    if "%MCP_MODE%"=="0" pause >nul
    exit /b 1
)
echo    [OK] Ollama operacional. >&2

:: ── PASSO 3: Container Postgres ──────────────────────────────────────────────
echo [3/5] Verificando container PostgreSQL (%POSTGRES_CONTAINER%)... >&2
echo [3/5] Verificando Postgres >> "%START_LOG%"

docker inspect --format="{{.State.Running}}" %POSTGRES_CONTAINER% 2>nul | findstr "true" >nul
if !ERRORLEVEL! equ 0 goto :CONTAINER_RUNNING

echo    [!] Container nao esta rodando. Iniciando via docker compose... >&2
echo    [!] Container parado. Iniciando... >> "%START_LOG%"
cd /d "%PROJECT_ROOT%"
docker compose up -d >> "%START_LOG%" 2>&1
if !ERRORLEVEL! neq 0 (
    echo [ERRO] Falha ao executar 'docker compose up -d'. >&2
    echo [ERRO] Falha no docker compose up >> "%START_LOG%"
    echo [!] Veja detalhes em: %START_LOG% >&2
    echo. >&2
    if "%MCP_MODE%"=="0" pause >nul
    exit /b 1
)
echo    [OK] Container iniciado. Aguardando PostgreSQL (max %MAX_WAIT_SECS%s)... >&2
set "WAITED=0"

:WAIT_LOOP
docker exec %POSTGRES_CONTAINER% pg_isready -U user -d mcp_knowledge >nul 2>&1
if !ERRORLEVEL! equ 0 goto :POSTGRES_READY
set /a "WAITED+=2"
if !WAITED! geq %MAX_WAIT_SECS% (
    echo [ERRO] Postgres nao ficou pronto em %MAX_WAIT_SECS%s. >&2
    echo [ERRO] Timeout aguardando Postgres >> "%START_LOG%"
    docker logs --tail 15 %POSTGRES_CONTAINER% >> "%START_LOG%" 2>&1
    echo [!] Veja logs em: %START_LOG% >&2
    echo. >&2
    if "%MCP_MODE%"=="0" pause >nul
    exit /b 1
)
timeout /t 2 /nobreak >nul
goto :WAIT_LOOP

:POSTGRES_READY
echo    [OK] PostgreSQL pronto (aguardou !WAITED!s). >&2
echo    [OK] Postgres pronto apos !WAITED!s >> "%START_LOG%"
goto :STEP_4

:CONTAINER_RUNNING
docker exec %POSTGRES_CONTAINER% pg_isready -U user -d mcp_knowledge >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo    [!] Container rodando mas Postgres nao responde. Reiniciando... >&2
    docker restart %POSTGRES_CONTAINER% >> "%START_LOG%" 2>&1
    timeout /t 5 /nobreak >nul
    docker exec %POSTGRES_CONTAINER% pg_isready -U user -d mcp_knowledge >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [ERRO] Postgres nao responde apos reinicio. >&2
        echo [ERRO] Postgres nao responde apos reinicio >> "%START_LOG%"
        docker logs --tail 15 %POSTGRES_CONTAINER% >> "%START_LOG%" 2>&1
        echo [!] Veja logs em: %START_LOG% >&2
        echo. >&2
        if "%MCP_MODE%"=="0" pause >nul
        exit /b 1
    )
    echo    [OK] Postgres recuperado apos reinicio. >&2
) else (
    echo    [OK] Container rodando e saudavel. >&2
)

:STEP_4

:: ── PASSO 4: Dependências Python ─────────────────────────────────────────────
echo [4/5] Validando bibliotecas Python... >&2
echo [4/5] Validando libs Python >> "%START_LOG%"
"%PYTHON_EXE%" -c "import langchain_text_splitters, psycopg2, chromadb, ollama" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo    [!] Bibliotecas faltando. Instalando requirements.txt... >&2
    "%PYTHON_EXE%" -m pip install -r "%PROJECT_ROOT%requirements.txt" --quiet >> "%START_LOG%" 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [ERRO] Falha ao instalar dependencias. >&2
        echo [ERRO] Falha no pip install >> "%START_LOG%"
        echo [!] Tente manualmente: .venv\Scripts\pip install -r requirements.txt >&2
        echo [!] Detalhes em: %START_LOG% >&2
        echo. >&2
        if "%MCP_MODE%"=="0" pause >nul
        exit /b 1
    )
    echo    [OK] Dependencias instaladas. >&2
) else (
    echo    [OK] Bibliotecas validadas. >&2
)

:: ── PASSO 5: Inicia servidor ──────────────────────────────────────────────────
echo [5/5] Iniciando Servidor MCP (Modo STDIO)... >&2
echo [5/5] Iniciando servidor >> "%START_LOG%"
echo ---------------------------------------------------------- >&2
echo [INFO] Log do servidor: %MCP_LOG% >&2
echo [INFO] CTRL+C para encerrar. >&2
echo ---------------------------------------------------------- >&2
echo. >&2

"%PYTHON_EXE%" -u -m src.main
set "EXIT_CODE=!ERRORLEVEL!"

echo. >&2
if !EXIT_CODE! equ 0 (
    echo [INFO] Servidor encerrado normalmente. >&2
    echo [INFO] Servidor encerrado normalmente >> "%START_LOG%"
) else (
    echo [ALERTA] Servidor parou com erro (codigo: !EXIT_CODE!). >&2
    echo [ALERTA] Servidor parou com codigo !EXIT_CODE! >> "%START_LOG%"
    echo. >&2
    echo Ultimas linhas do log do servidor: >&2
    echo ---------------------------------------------------------- >&2
    if exist "%MCP_LOG%" powershell -Command "Get-Content '%MCP_LOG%' -Tail 15" 2>nul >&2
    echo ---------------------------------------------------------- >&2
)

echo. >&2
if "%MCP_MODE%"=="0" (
    echo Pressione qualquer tecla para fechar... >&2
    pause >nul
)
