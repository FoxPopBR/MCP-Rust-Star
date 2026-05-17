param(
    [ValidateSet("stdio","streamable-http")]
    [string]$Transport
)

$Root = Split-Path $PSScriptRoot -Parent
$Venv = Join-Path $Root ".venv\Scripts\python.exe"

$env:PYTHONPATH = $Root
$env:VECTOR_STORE_TYPE = "postgres"

Write-Host "=== MCP Rust Star Knowledge Server ===" -ForegroundColor Cyan
Write-Host "Uso: .\start_server.ps1 [-Transport stdio|streamable-http]" -ForegroundColor DarkGray
Write-Host "Padrao: streamable-http  (http://127.0.0.1:8765/mcp)" -ForegroundColor Green
Write-Host ""

$extra = @()
if ($Transport) { $extra = @("--transport", $Transport) }

& $Venv -m src.main @extra
