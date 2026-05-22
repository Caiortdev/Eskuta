# =============================================================
# Eskuta — Gera par de chaves Ed25519 pra assinar releases.
# =============================================================
#
# Use UMA vez por projeto. A chave pública vai pro tauri.conf.json
# (committada no repo). A chave privada NUNCA vai pro git — armazene
# num lugar seguro (1Password, GitHub Secrets pra CI, etc).
#
# Após rodar:
#   1. Cole o conteúdo de eskuta-update.key.pub em tauri.conf.json
#      em "plugins.updater.pubkey"
#   2. Guarde eskuta-update.key em local seguro
#   3. Configure GITHUB_SECRET TAURI_PRIVATE_KEY com o conteúdo dela
#   4. Configure GITHUB_SECRET TAURI_KEY_PASSWORD com a senha que digitou
#   5. Mude tauri.conf.json -> plugins.updater.active = true
# =============================================================

param(
    [string]$OutputDir = "./tmp"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
}

$PrivKey = Join-Path $OutputDir "eskuta-update.key"
$PubKey = Join-Path $OutputDir "eskuta-update.key.pub"

if (Test-Path $PrivKey) {
    Write-Host "❌ Chave privada já existe em $PrivKey" -ForegroundColor Red
    Write-Host "   Apague antes de gerar uma nova (CUIDADO: rotacionar quebra updates dos clientes antigos)"
    exit 1
}

Write-Host "🔐 Gerando par de chaves Ed25519 via tauri CLI..." -ForegroundColor Cyan
Write-Host ""
Write-Host "Você vai ser perguntado por uma SENHA pra a chave privada."
Write-Host "Use uma senha forte e GUARDE-A — sem ela você não consegue assinar futuras releases."
Write-Host ""

# tauri signer generate gera <output>.pub junto
& npx tauri signer generate -w $PrivKey
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Falha ao gerar chaves" -ForegroundColor Red
    exit 1
}

# Verifica arquivos gerados
if (-not (Test-Path $PrivKey)) {
    Write-Host "❌ Chave privada não foi criada em $PrivKey" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $PubKey)) {
    Write-Host "❌ Chave pública não foi criada em $PubKey" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅ Chaves geradas!" -ForegroundColor Green
Write-Host ""
Write-Host "Chave pública (cole no tauri.conf.json):" -ForegroundColor Cyan
Get-Content $PubKey
Write-Host ""
Write-Host "Próximos passos:" -ForegroundColor Yellow
Write-Host "  1. Abra src-tauri/tauri.conf.json e cole essa pubkey em plugins.updater.pubkey"
Write-Host "  2. Mude plugins.updater.active de false pra true"
Write-Host "  3. Configure os secrets do GitHub Actions:"
Write-Host "       TAURI_PRIVATE_KEY  = conteúdo de $PrivKey"
Write-Host "       TAURI_KEY_PASSWORD = senha que você digitou agora"
Write-Host "  4. GUARDE $PrivKey num lugar seguro (1Password, etc) e APAGUE do disco local."
Write-Host "  5. Adicione $OutputDir/ ao .gitignore (já está)"
