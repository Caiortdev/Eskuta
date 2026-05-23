# =============================================================
# Eskuta - Modo desenvolvimento (sem build/empacotamento)
# =============================================================
#
# Sobe sidecar Python + frontend Vite em paralelo. App abre no
# browser comum (Chrome/Edge) com DevTools (F12) habilitado.
#
# Uso:
#   pwsh scripts/dev.ps1       (PowerShell 7+)
#   powershell.exe -ExecutionPolicy Bypass -File scripts/dev.ps1
#
# Pra parar tudo: feche os 2 terminais que abrir, OU Ctrl+C neste.
# =============================================================

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "=== Eskuta - modo dev ===" -ForegroundColor Cyan
Write-Host "Root: $ProjectRoot"
Write-Host ""

# 1. Mata processos zombies
Get-Process -Name "eskuta-sidecar","python" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "*eskuta*" -or $_.Path -like "*MeusProjetos*" } |
    Stop-Process -Force -ErrorAction SilentlyContinue

# 2. Verifica venv
$venvPython = Join-Path $ProjectRoot "src-python\venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[ERRO] venv nao existe em $venvPython" -ForegroundColor Red
    Write-Host "Crie com: cd src-python; python -m venv venv; .\venv\Scripts\activate; pip install -r requirements.txt -r requirements-dev.txt"
    exit 1
}

# 3. Verifica node_modules
if (-not (Test-Path (Join-Path $ProjectRoot "node_modules"))) {
    Write-Host "[ERRO] node_modules nao existe. Rode 'npm install' primeiro." -ForegroundColor Red
    exit 1
}

# 4. Inicia sidecar em terminal separado
Write-Host "[1/2] Iniciando sidecar Python na porta 8765..." -ForegroundColor Yellow
$sidecarCmd = "& '$venvPython' -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload"
Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$ProjectRoot\src-python'; Write-Host '=== SIDECAR (Ctrl+C pra parar) ===' -ForegroundColor Cyan; $sidecarCmd"
) -WindowStyle Normal

# 5. Espera sidecar subir
Write-Host "Aguardando sidecar subir (max 15s)..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
}
if (-not $ready) {
    Write-Host "[ERRO] Sidecar nao respondeu em 15s. Ve o terminal SIDECAR." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Sidecar respondendo em http://127.0.0.1:8765" -ForegroundColor Green

# 6. Inicia frontend Vite em terminal separado
Write-Host ""
Write-Host "[2/2] Iniciando frontend Vite na porta 1420..." -ForegroundColor Yellow
Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$ProjectRoot'; Write-Host '=== FRONTEND VITE (Ctrl+C pra parar) ===' -ForegroundColor Cyan; npm run dev"
) -WindowStyle Normal

# 7. Espera Vite subir
Write-Host "Aguardando Vite subir (max 30s)..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:1420" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
}
if (-not $ready) {
    Write-Host "[AVISO] Vite nao respondeu em 30s. Tentando abrir browser mesmo assim." -ForegroundColor Yellow
}

# 8. Abre no Chrome com DevTools
Write-Host ""
Write-Host "[OK] App pronto! Abrindo http://localhost:1420" -ForegroundColor Green
Write-Host ""
Write-Host "=== PRA DEBUGAR ===" -ForegroundColor Cyan
Write-Host "1. Pressione F12 pra abrir DevTools"
Write-Host "2. Aba 'Network' pra ver chamadas HTTP"
Write-Host "3. Aba 'Console' pra ver erros JS"
Write-Host "4. Reproduza o bug (ex: ir em Configuracoes)"
Write-Host "5. Olhe a requisicao vermelha em Network - clica e ve detalhes"
Write-Host ""
Write-Host "Pra parar: feche os 2 terminais que abriram (sidecar + vite)."
Write-Host ""

Start-Process "http://localhost:1420"
