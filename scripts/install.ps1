[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
. "$PSScriptRoot\diagnostico.ps1"

if (-not (Test-CreativeHubPrerequisites)) {
    throw "Instalacao interrompida: corrija os pre-requisitos indicados acima e execute este script novamente."
}

$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & python -m venv (Join-Path $repositoryRoot ".venv")
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $repositoryRoot "requirements.txt")

Push-Location (Join-Path $repositoryRoot "creative_hub\headline_studio")
try {
    & npm ci
    & npm run build
}
finally {
    Pop-Location
}

Write-Host "Creative Hub instalado. Execute .\scripts\abrir-hub.ps1 para iniciar." -ForegroundColor Green
