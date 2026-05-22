# =============================================================
# Eskuta — Build pipeline (Windows)
# =============================================================
#
# Compila o app inteiro num único MSI/NSIS:
#   1. Empacota o sidecar Python via PyInstaller (build_sidecar.py)
#   2. Renomeia o binário pro target triple esperado pelo Tauri
#   3. Builda o frontend React (vite build)
#   4. Builda o Tauri (que assina + gera MSI/NSIS)
#
# Saída final em: src-tauri/target/release/bundle/{msi,nsis}/
#
# Pré-requisitos:
#   - Python 3.11 + venv com requirements + requirements-build.txt
#   - Node 20+
#   - Rust toolchain (rustup, target x86_64-pc-windows-msvc)
#   - WiX Toolset 3.x (pra gerar MSI) — instalado automaticamente pelo Tauri
#
# Uso:
#   pwsh scripts/build.ps1                    # build completo
#   pwsh scripts/build.ps1 -SkipSidecar       # pula o build do Python
#   pwsh scripts/build.ps1 -CleanFirst        # rm -rf dist/ + build/ antes
# =============================================================

param(
    [switch]$SkipSidecar,
    [switch]$CleanFirst
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "🦅 Eskuta — build pipeline" -ForegroundColor Cyan
Write-Host "   Root: $ProjectRoot"
Write-Host ""

# -------------------------------------------------------------
# 1. Sidecar Python
# -------------------------------------------------------------
if (-not $SkipSidecar) {
    Write-Host "🐍 1/4 — Empacotando sidecar Python via PyInstaller..." -ForegroundColor Yellow

    $SidecarRoot = Join-Path $ProjectRoot "src-python"
    $VenvPython = Join-Path $SidecarRoot "venv\Scripts\python.exe"

    if (-not (Test-Path $VenvPython)) {
        Write-Host "❌ venv não encontrada em $VenvPython" -ForegroundColor Red
        Write-Host "   Rode: cd src-python; python -m venv venv; .\venv\Scripts\activate; pip install -r requirements.txt -r requirements-build.txt"
        exit 1
    }

    Push-Location $SidecarRoot
    try {
        if ($CleanFirst) {
            & $VenvPython build_sidecar.py --clean-only
        }
        & $VenvPython build_sidecar.py
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ build_sidecar.py falhou (exit $LASTEXITCODE)" -ForegroundColor Red
            exit 1
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "⏭️  1/4 — Sidecar (skip, flag -SkipSidecar ativo)" -ForegroundColor DarkGray
}

# -------------------------------------------------------------
# 2. Copy + rename pro target triple
# -------------------------------------------------------------
Write-Host ""
Write-Host "📦 2/4 — Copiando binário pra src-tauri/binaries/..." -ForegroundColor Yellow

# Descobre o target triple do Rust
$Target = (& rustc -vV) | Select-String -Pattern "host: " | ForEach-Object { ($_ -split ": ")[1].Trim() }
if (-not $Target) {
    Write-Host "❌ rustc não encontrado. Instale Rust via rustup." -ForegroundColor Red
    exit 1
}
Write-Host "   Target triple: $Target"

$SrcBinary = Join-Path $ProjectRoot "src-python\dist\eskuta-sidecar.exe"
$DstBinaryDir = Join-Path $ProjectRoot "src-tauri\binaries"
$DstBinary = Join-Path $DstBinaryDir "eskuta-sidecar-$Target.exe"

if (-not (Test-Path $SrcBinary)) {
    Write-Host "❌ Binário do sidecar não existe em $SrcBinary" -ForegroundColor Red
    Write-Host "   Rode sem -SkipSidecar pra empacotar primeiro."
    exit 1
}

New-Item -ItemType Directory -Force -Path $DstBinaryDir | Out-Null
Copy-Item -Path $SrcBinary -Destination $DstBinary -Force
$SizeMb = [math]::Round((Get-Item $DstBinary).Length / 1MB, 1)
Write-Host "   ✓ $DstBinary ($SizeMb MB)"

# -------------------------------------------------------------
# 3. Frontend React (Vite)
# -------------------------------------------------------------
Write-Host ""
Write-Host "⚛️  3/4 — Buildando frontend React (Vite)..." -ForegroundColor Yellow

Push-Location $ProjectRoot
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ npm run build falhou" -ForegroundColor Red
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
Write-Host "🦀 4/4 — Buildando Tauri (MSI + NSIS)..." -ForegroundColor Yellow

Push-Location $ProjectRoot
try {
    & npm run tauri build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ tauri build falhou" -ForegroundColor Red
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
Write-Host "✅ Build completo!" -ForegroundColor Green
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
