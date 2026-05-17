@echo off
setlocal

set PID_FILE=%~dp0..\data\server.pid

if not exist "%PID_FILE%" (
    echo Servidor nao esta rodando ^(PID file nao encontrado^).
    exit /b 1
)

set /p PID=<"%PID_FILE%"
echo Encerrando servidor MCP Rust Star ^(PID=%PID%^)...
taskkill /PID %PID% /F >nul 2>&1

if %ERRORLEVEL% == 0 (
    echo Servidor encerrado com sucesso.
) else (
    echo Falha ao encerrar processo. Pode ja ter sido encerrado.
)

endlocal
