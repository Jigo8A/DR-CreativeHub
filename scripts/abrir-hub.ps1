[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$hubRoot = Join-Path $repositoryRoot "creative_hub"
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$url = "http://127.0.0.1:8092"

if (-not (Test-Path $venvPython)) {
    throw "Instalacao nao encontrada. Execute .\scripts\install.ps1 primeiro."
}

$listening = Get-NetTCPConnection -LocalPort 8092 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Start-Process -FilePath $venvPython -ArgumentList "app.py" -WorkingDirectory $hubRoot -WindowStyle Hidden
    Start-Sleep -Seconds 1
}

if (-not $NoBrowser) {
    Start-Process $url
}
