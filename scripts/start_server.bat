@echo off
setlocal

set ROOT=%~dp0..
set VENV=%ROOT%\.venv\Scripts\python.exe
set PYTHONPATH=%ROOT%
set VECTOR_STORE_TYPE=postgres

echo === MCP Rust Star Knowledge Server ===
echo Uso: start_server.bat [--transport streamable-http^|stdio]
echo Padrao: streamable-http  (http://127.0.0.1:8765/mcp)
echo.

"%VENV%" -m src.main %*

endlocal
