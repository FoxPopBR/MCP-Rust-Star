@echo off
title MCP Rust Star - Dashboard Elite de Monitoramento
cls
set PYTHONPATH=.

REM Defesa em profundidade: encerra qualquer dashboard antigo antes de iniciar.
REM O Python tambem faz isso em _enforce_single_instance, mas se um lancamento
REM anterior travou antes desse ponto o .bat e o ultimo recurso de limpeza.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'dashboard' } | ForEach-Object { Write-Host '[dashboard.bat] killing PID' $_.ProcessId; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

python -m dashboard
pause
