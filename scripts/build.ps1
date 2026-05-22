# =============================================================
# Eskuta - Build pipeline (Windows)
# =============================================================
#
# Compila o app inteiro num unico MSI/NSIS:
#   1. Empacota o sidecar Python via PyInstaller (build_sidecar.py)
#   2. Renomeia o binario pro target triple esperado pelo Tauri
#   3. Builda o frontend React (vite build)
#   4. Builda o Tauri (que assina + gera MSI/NSIS)
#
# Saida final em: src-tauri/target/release/bundle/{msi,nsis}/
#
# Pre-requisitos:
#   - Python 3.11 + venv com requirements + requirements-build.txt
#   - Node 20+
#   - Rust toolchain (rustup, target x86_64-pc-windows-msvc)
#   - WiX Toolset 3.x (pra gerar MSI) - instalado automaticamente pelo Tauri
#
# Uso (PowerShell 5.1+):
#   powershell.exe -ExecutionPolicy Bypass -File scripts/build.ps1
#   pwsh scripts/build.ps1                    # PowerShell 7+
#   ... -SkipSidecar       # pula o build do Python
#   ... -CleanFirst        # rm -rf dist/ + build/ antes
# =============================================================

param(
    [switch]$SkipSidecar,
    [switch]$CleanFirst
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "=== Eskuta - build pipeline ===" -ForegroundColor Cyan
Write-Host "Root: $ProjectRoot"
Write-Host ""

# -------------------------------------------------------------
# 1. Sidecar Python
# -------------------------------------------------------------
if (-not $SkipSidecar) {
    Write-Host "[1/4] Empacotando sidecar Python via PyInstaller..." -ForegroundColor Yellow

    $SidecarRoot = Join-Path $ProjectRoot "src-python"
    $VenvPython = Join-Path $SidecarRoot "venv\Scripts\python.exe"

    if (-not (Test-Path $VenvPython)) {
        Write-Host "[ERRO] venv nao encontrada em $VenvPython" -ForegroundColor Red
        Write-Host "       Rode: cd src-python; python -m venv venv; .\venv\Scripts\activate; pip install -r requirements.txt -r requirements-build.txt"
        exit 1
    }

    Push-Location $SidecarRoot
    try {
        if ($CleanFirst) {
            & $VenvPython build_sidecar.py --clean-only
        }
        & $VenvPython build_sidecar.py
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERRO] build_sidecar.py falhou (exit $LASTEXITCODE)" -ForegroundColor Red
            exit 1
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "[SKIP] 1/4 - Sidecar (flag -SkipSidecar ativo)" -ForegroundColor DarkGray
}

# -------------------------------------------------------------
# 2. Copy pasta do sidecar pra src-tauri/binaries/
# -------------------------------------------------------------
# Com PyInstaller --onedir, o sidecar fica em src-python/dist/eskuta-sidecar/
# (pasta com .exe + _internal/ ao lado). Copiamos a pasta inteira pra
# src-tauri/binaries/eskuta-sidecar/ — bundle.resources do tauri.conf.json
# pega essa pasta e empacota como resources/sidecar/ no instalador final.
Write-Host ""
Write-Host "[2/4] Copiando pasta do sidecar pra src-tauri/binaries/..." -ForegroundColor Yellow

$SrcDir = Join-Path $ProjectRoot "src-python\dist\eskuta-sidecar"
$DstDir = Join-Path $ProjectRoot "src-tauri\binaries\eskuta-sidecar"

if (-not (Test-Path $SrcDir)) {
    Write-Host "[ERRO] Pasta do sidecar nao existe em $SrcDir" -ForegroundColor Red
    Write-Host "       Rode sem -SkipSidecar pra empacotar primeiro."
    exit 1
}

if (Test-Path $DstDir) { Remove-Item -Recurse -Force $DstDir }
New-Item -ItemType Directory -Force -Path $DstDir | Out-Null

# Copia tudo (.exe + _internal/) — preserva estrutura interna do PyInstaller
Copy-Item -Path "$SrcDir\*" -Destination $DstDir -Recurse -Force

$totalSize = (Get-ChildItem $DstDir -Recurse | Measure-Object Length -Sum).Sum
$SizeMb = [math]::Round($totalSize / 1MB, 1)
$fileCount = (Get-ChildItem $DstDir -Recurse -File).Count
Write-Host "      [OK] $DstDir ($fileCount arquivos, $SizeMb MB)"

# -------------------------------------------------------------
# 3. Frontend React (Vite)
# -------------------------------------------------------------
Write-Host ""
Write-Host "[3/4] Buildando frontend React (Vite)..." -ForegroundColor Yellow

Push-Location $ProjectRoot
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERRO] npm run build falhou" -ForegroundColor Red
        exit 1
    }
}
finally {
    Pop-Location
}

# -------------------------------------------------------------
# 4. Tauri build (junta tudo + assina + gera installers)
# -------------------------------------------------------------
Write-Host ""
Write-Host "[4/4] Buildando Tauri (MSI + NSIS)..." -ForegroundColor Yellow

Push-Location $ProjectRoot
try {
    & npm run tauri build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERRO] tauri build falhou" -ForegroundColor Red
        exit 1
    }
}
finally {
    Pop-Location
}

# -------------------------------------------------------------
# Resultado
# -------------------------------------------------------------
Write-Host ""
Write-Host "[OK] Build completo!" -ForegroundColor Green
Write-Host ""
Write-Host "Instaladores em:" -ForegroundColor Cyan
$BundleRoot = Join-Path $ProjectRoot "src-tauri\target\release\bundle"
if (Test-Path "$BundleRoot\msi") {
    Get-ChildItem -Path "$BundleRoot\msi" -Filter *.msi | ForEach-Object {
        $sz = [math]::Round($_.Length / 1MB, 1)
        Write-Host "   $($_.FullName)  ($sz MB)"
    }
}
if (Test-Path "$BundleRoot\nsis") {
    Get-ChildItem -Path "$BundleRoot\nsis" -Filter *.exe | ForEach-Object {
        $sz = [math]::Round($_.Length / 1MB, 1)
        Write-Host "   $($_.FullName)  ($sz MB)"
    }
}
