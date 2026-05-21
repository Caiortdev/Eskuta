<#
.SYNOPSIS
    Preflight check do ambiente de desenvolvimento do Eskuta.

.DESCRIPTION
    Valida que todas as ferramentas exigidas pela Fase 0 do RELATORIO_TECNICO.md
    estão instaladas e nas versões esperadas. É idempotente — pode ser rodado
    quantas vezes quiser sem efeito colateral.

    Exit code:
      0  -> todas as ferramentas OK
      1  -> uma ou mais ferramentas faltando / em versão incompatível

.EXAMPLE
    pwsh scripts/preflight.ps1
#>

[CmdletBinding()]
param(
    [switch] $Json
)

$ErrorActionPreference = 'Stop'
$script:Results = @()

# Atualiza o PATH desta sessão a partir do registro pra pegar ferramentas
# instaladas via winget após o shell ter iniciado (ex: ffmpeg).
$machinePath = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
$userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
$env:Path = "$machinePath;$userPath"

function Test-Tool {
    param(
        [string] $Name,
        [scriptblock] $Probe,
        [string] $Required,
        [string] $InstallHint
    )
    $status = 'fail'
    $detail = ''
    try {
        $version = & $Probe
        if ($null -ne $version -and $version -ne '') {
            $status = 'ok'
            $detail = $version
        }
        else {
            $detail = 'comando rodou mas n�o retornou vers�o'
        }
    }
    catch {
        $detail = $_.Exception.Message
    }

    $script:Results += [pscustomobject]@{
        name        = $Name
        required    = $Required
        status      = $status
        detail      = $detail
        installHint = $InstallHint
    }
}

# --- Node.js >= 20 ---
Test-Tool -Name 'Node.js' -Required '>= 20.x' -InstallHint 'https://nodejs.org/' -Probe {
    $v = (node --version 2>$null)
    if ($v -match '^v(\d+)\.') {
        $major = [int]$matches[1]
        if ($major -lt 20) { throw "Node $v < 20" }
        return $v
    }
    throw 'node nao encontrado'
}

# --- npm ---
Test-Tool -Name 'npm' -Required 'qualquer' -InstallHint 'vem junto com Node.js' -Probe {
    return (npm --version 2>$null)
}

# --- Rust / Cargo ---
Test-Tool -Name 'Rust toolchain' -Required 'stable' -InstallHint 'https://rustup.rs' -Probe {
    return ((rustc --version 2>$null) -split "`n")[0]
}
Test-Tool -Name 'Cargo' -Required 'stable' -InstallHint 'vem junto com Rust' -Probe {
    return ((cargo --version 2>$null) -split "`n")[0]
}

# --- Python 3.11 (essencial pro sidecar; pyannote nao roda em 3.12+) ---
Test-Tool -Name 'Python 3.11' -Required '3.11.x' -InstallHint 'py install 3.11' -Probe {
    $v = (py -3.11 --version 2>$null)
    if (-not $v) { throw 'Python 3.11 nao encontrado (3.12+ nao serve pra pyannote)' }
    if ($v -notmatch '^Python 3\.11\.') { throw "Versao errada: $v" }
    return $v
}

# --- FFmpeg ---
Test-Tool -Name 'FFmpeg' -Required 'qualquer' -InstallHint 'winget install Gyan.FFmpeg' -Probe {
    $line = (ffmpeg -version 2>$null | Select-Object -First 1)
    if (-not $line) { throw 'ffmpeg nao no PATH' }
    return $line
}

# --- Git ---
Test-Tool -Name 'Git' -Required 'qualquer' -InstallHint 'https://git-scm.com' -Probe {
    return (git --version 2>$null)
}

# --- WebView2 (Windows) ---
Test-Tool -Name 'WebView2' -Required 'qualquer (Win11 nativo)' -InstallHint 'https://developer.microsoft.com/microsoft-edge/webview2/' -Probe {
    $regPath = 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    if (Test-Path $regPath) {
        $pv = (Get-ItemProperty $regPath).pv
        if ($pv) { return "v$pv" }
    }
    throw 'WebView2 nao encontrado no registro'
}

# --- VS C++ Build Tools (Tauri precisa pra link no Windows) ---
Test-Tool -Name 'VS C++ Build Tools' -Required 'instalado' -InstallHint 'https://aka.ms/vs/17/release/vs_BuildTools.exe' -Probe {
    $vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path $vswhere)) { throw 'vswhere.exe nao instalado' }
    $vc = & $vswhere -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath -latest
    if (-not $vc) { throw 'VC.Tools.x86.x64 nao instalado' }
    return $vc
}

# --- Output ---
if ($Json) {
    $script:Results | ConvertTo-Json -Depth 3
    return
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Eskuta -- Preflight check (Fase 0)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$failures = 0
foreach ($r in $script:Results) {
    if ($r.status -eq 'ok') {
        Write-Host ("  [OK] {0,-22} {1}" -f $r.name, $r.detail) -ForegroundColor Green
    }
    else {
        Write-Host ("  [!!] {0,-22} {1}" -f $r.name, $r.detail) -ForegroundColor Red
        Write-Host ("       Instalacao: {0}" -f $r.installHint) -ForegroundColor Yellow
        $failures++
    }
}

Write-Host ""
if ($failures -eq 0) {
    Write-Host "Tudo certo. Pode rodar 'npm run tauri dev'." -ForegroundColor Green
    exit 0
}
else {
    Write-Host ("$failures ferramenta(s) faltando. Instale antes de continuar.") -ForegroundColor Red
    exit 1
}
