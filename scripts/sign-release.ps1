# =============================================================
# Eskuta — Assina um build de release pra publicar via auto-update.
# =============================================================
#
# O que faz:
#   1. Lê o binário gerado pelo Tauri (src-tauri/target/release/bundle/)
#   2. Assina o NSIS .exe com a chave Ed25519 privada (via tauri signer sign)
#   3. Gera o arquivo de assinatura .sig
#   4. Emite um trecho de manifesto JSON pra você colar no servidor
#
# Pré-requisitos:
#   - Já rodou scripts/build.ps1 (existe o .msi/.exe em target/release/bundle/)
#   - Variável de ambiente TAURI_PRIVATE_KEY contém a chave privada
#     (ou usar -PrivateKeyPath pra arquivo)
#   - Variável de ambiente TAURI_KEY_PASSWORD contém a senha
#     (ou usar -KeyPassword)
#   - Version segue semver (ex: "0.1.1")
#
# Uso:
#   pwsh scripts/sign-release.ps1 -Version "0.1.1"
#   pwsh scripts/sign-release.ps1 -Version "0.1.1" -PrivateKeyPath ./tmp/eskuta-update.key
# =============================================================

param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$PrivateKeyPath,
    [string]$KeyPassword,
    [string]$ReleaseNotes = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# Resolve chave privada
if ($PrivateKeyPath) {
    if (-not (Test-Path $PrivateKeyPath)) {
        Write-Host "❌ Chave privada não encontrada em $PrivateKeyPath" -ForegroundColor Red
        exit 1
    }
    $env:TAURI_PRIVATE_KEY = Get-Content $PrivateKeyPath -Raw
}
if ($KeyPassword) {
    $env:TAURI_KEY_PASSWORD = $KeyPassword
}

if (-not $env:TAURI_PRIVATE_KEY) {
    Write-Host "❌ Variável TAURI_PRIVATE_KEY não definida e -PrivateKeyPath não passado." -ForegroundColor Red
    exit 1
}
if (-not $env:TAURI_KEY_PASSWORD) {
    Write-Host "⚠️  TAURI_KEY_PASSWORD não definida — vai pedir interativamente."
}

# Localiza o NSIS exe (assinamos esse pro updater porque é menor que o MSI)
$BundleNsis = Join-Path $ProjectRoot "src-tauri\target\release\bundle\nsis"
if (-not (Test-Path $BundleNsis)) {
    Write-Host "❌ Bundle NSIS não encontrado em $BundleNsis" -ForegroundColor Red
    Write-Host "   Rode scripts/build.ps1 primeiro." -ForegroundColor Red
    exit 1
}

$Installer = Get-ChildItem -Path $BundleNsis -Filter "*-setup.exe" | Select-Object -First 1
if (-not $Installer) {
    Write-Host "❌ Não encontrei o instalador NSIS em $BundleNsis" -ForegroundColor Red
    exit 1
}

Write-Host "📦 Instalador: $($Installer.FullName)" -ForegroundColor Cyan
Write-Host "   Tamanho: $([math]::Round($Installer.Length / 1MB, 1)) MB"
Write-Host "   Version pedida: $Version"
Write-Host ""

# Tauri 2 gera .sig junto do bundle quando TAURI_PRIVATE_KEY está setado.
# Mas se você quer (re-)assinar manualmente um bundle existente:
$SigFile = "$($Installer.FullName).sig"
if (Test-Path $SigFile) {
    Write-Host "⚠️  .sig já existe em $SigFile — usando o existente." -ForegroundColor Yellow
}
else {
    Write-Host "🔏 Assinando com tauri signer sign..." -ForegroundColor Yellow
    & npx tauri signer sign -f $env:TAURI_PRIVATE_KEY -p $env:TAURI_KEY_PASSWORD $Installer.FullName
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Falha ao assinar" -ForegroundColor Red
        exit 1
    }
}

$Signature = Get-Content $SigFile -Raw
$Signature = $Signature.Trim()

# Calcula SHA256 pra documentação (não obrigatório pelo updater, mas útil)
$Hash = (Get-FileHash $Installer.FullName -Algorithm SHA256).Hash.ToLower()

Write-Host ""
Write-Host "✅ Pronto!" -ForegroundColor Green
Write-Host ""
Write-Host "Próximo passo: faça upload de:" -ForegroundColor Cyan
Write-Host "   $($Installer.FullName)"
Write-Host "   $SigFile"
Write-Host "pro seu servidor de updates (Cloudflare R2, S3, GitHub Releases, etc)."
Write-Host ""
Write-Host "Manifesto JSON pra publicar no endpoint:" -ForegroundColor Cyan
Write-Host ""

$ReleaseDate = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$DownloadUrl = "https://eskuta-updates.example.com/releases/v$Version/$($Installer.Name)"

$Manifest = @"
{
  "version": "$Version",
  "notes": "$ReleaseNotes",
  "pub_date": "$ReleaseDate",
  "sha256": "$Hash",
  "platforms": {
    "windows-x86_64": {
      "signature": "$Signature",
      "url": "$DownloadUrl"
    }
  }
}
"@

Write-Host $Manifest
Write-Host ""
Write-Host "Esse JSON deve ser servido pelo endpoint configurado em tauri.conf.json:"
Write-Host "  plugins.updater.endpoints[0] = $($env:TAURI_UPDATE_ENDPOINT ?? 'https://eskuta-updates.example.com/{{target}}/{{arch}}/{{current_version}}')"
