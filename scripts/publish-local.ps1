# =============================================================
# Eskuta — Organiza os instaladores buildados numa pasta acessível
# pra você compartilhar com usuários (drag pra pen drive, anexar
# em email, subir pro Google Drive, etc).
#
# Roda DEPOIS de `pwsh scripts/build.ps1`.
#
# Saída: D:\MeusProjetos\Eskuta\releases\v<versao>\
#   ├── Eskuta_<versao>_x64-setup.exe       (instalador NSIS — recomendado pro usuário final)
#   ├── Eskuta_<versao>_x64_pt-BR.msi       (instalador MSI — corporativo)
#   ├── *.sig                                (assinaturas Ed25519, se TAURI_PRIVATE_KEY setado)
#   ├── RELEASE_NOTES.md                     (gerado do CHANGELOG)
#   └── COMO_INSTALAR.txt                    (instrução em PT-BR pro user final)
# =============================================================

param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

$BundleRoot = Join-Path $ProjectRoot "src-tauri\target\release\bundle"
$ReleasesRoot = Join-Path $ProjectRoot "releases\v$Version"

if (-not (Test-Path $BundleRoot)) {
    Write-Host "[ERRO] Bundle nao existe em $BundleRoot" -ForegroundColor Red
    Write-Host "       Rode 'pwsh scripts/build.ps1' primeiro." -ForegroundColor Red
    exit 1
}

Write-Host "Eskuta - publish-local v$Version" -ForegroundColor Cyan
Write-Host "Destino: $ReleasesRoot"
Write-Host ""

# Cria pasta de destino
New-Item -ItemType Directory -Force -Path $ReleasesRoot | Out-Null

# 1. Copia MSI (se existir)
$msiPath = Join-Path $BundleRoot "msi"
if (Test-Path $msiPath) {
    Get-ChildItem -Path $msiPath -Filter "*.msi" | ForEach-Object {
        Copy-Item $_.FullName $ReleasesRoot -Force
        $size = [math]::Round($_.Length / 1MB, 1)
        Write-Host "  [OK] $($_.Name) ($size MB)" -ForegroundColor Green
    }
}

# 2. Copia NSIS (.exe + .sig)
$nsisPath = Join-Path $BundleRoot "nsis"
if (Test-Path $nsisPath) {
    Get-ChildItem -Path $nsisPath -Include "*.exe", "*.sig" -File -Recurse | ForEach-Object {
        Copy-Item $_.FullName $ReleasesRoot -Force
        $size = [math]::Round($_.Length / 1MB, 1)
        Write-Host "  [OK] $($_.Name) ($size MB)" -ForegroundColor Green
    }
}

# 3. Gera RELEASE_NOTES.md a partir do CHANGELOG (seção [Unreleased] ou [v$Version])
$changelog = Join-Path $ProjectRoot "CHANGELOG.md"
if (Test-Path $changelog) {
    $content = Get-Content $changelog -Raw
    # Pega a seção da versão atual
    $pattern = "(?ms)## \[$([regex]::Escape($Version))\].*?(?=^## \[|\z)"
    $match = [regex]::Match($content, $pattern)
    if ($match.Success) {
        $releaseNotes = $match.Value.Trim()
        Set-Content -Path (Join-Path $ReleasesRoot "RELEASE_NOTES.md") -Value $releaseNotes -Encoding UTF8
        Write-Host "  [OK] RELEASE_NOTES.md (extraido do CHANGELOG)" -ForegroundColor Green
    } else {
        Copy-Item $changelog (Join-Path $ReleasesRoot "RELEASE_NOTES.md") -Force
        Write-Host "  [INFO] CHANGELOG copiado inteiro (versao $Version nao encontrada na regex)" -ForegroundColor Yellow
    }
}

# 4. Gera COMO_INSTALAR.txt — instrução simples em PT-BR pro usuário final
$comoInstalar = @"
COMO INSTALAR O ESKUTA (Windows 10/11)
========================================

Voce recebeu 2 arquivos de instalador:

  Eskuta_${Version}_x64-setup.exe   <- Recomendado (instalador rapido)
  Eskuta_${Version}_x64_pt-BR.msi   <- Opcional (instalador empresarial)

Use APENAS UM dos dois.

PASSO A PASSO
--------------

1. Clique duas vezes em "Eskuta_${Version}_x64-setup.exe"

2. O Windows pode mostrar uma tela azul "Windows protegeu o seu PC":
   - Clique em "Mais informacoes"
   - Depois em "Executar mesmo assim"
   (Isso acontece porque o app ainda nao tem certificado digital de codigo.
    E seguro - o instalador foi gerado por voce / pela sua equipe.)

3. Siga o assistente de instalacao (Avancar > Avancar > Instalar)

4. Apos instalar, abra o "Eskuta" pelo Menu Iniciar

5. Na primeira execucao voce vai configurar as API keys de:
   - Pelo menos 1 STT (Groq recomendado - tem free tier)
   - Pelo menos 1 LLM (Claude recomendado pra qualidade)

   O proprio app mostra um modal passo-a-passo com link pra cada provider.

REQUISITOS DO SISTEMA
---------------------
- Windows 10 build 17763+ ou Windows 11
- WebView2 Runtime (geralmente ja instalado no Windows 11)
- Conexao com internet (pra chamar Groq/Claude/etc)
- Espaco em disco: ~500MB pra app + audio de reuniao

PRIVACIDADE
-----------
- Suas API keys ficam no Credential Manager do Windows (criptografado)
- O audio de reuniao fica no seu disco (~/.eskuta/uploads/)
- Nada e enviado pra um servidor externo - o app nao tem servidor
- A transcricao em texto vai pra Groq/AssemblyAI (STT) e o texto
  da transcricao vai pra Claude/GPT/Gemini (LLM) - voce paga
  diretamente esses provedores conforme uso

SUPORTE
-------
Em caso de problema, em Configuracoes > Diagnostico clique em
"Exportar logs" e envie o ZIP pro time tecnico (as API keys sao
mascaradas automaticamente).

Versao: $Version
Build: $(Get-Date -Format "yyyy-MM-dd HH:mm")
"@

Set-Content -Path (Join-Path $ReleasesRoot "COMO_INSTALAR.txt") -Value $comoInstalar -Encoding UTF8
Write-Host "  [OK] COMO_INSTALAR.txt" -ForegroundColor Green

# 5. Calcula SHA256 dos instaladores pra integrity check
$hashes = @{}
Get-ChildItem -Path $ReleasesRoot -Include "*.exe", "*.msi" -File | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    $hashes[$_.Name] = $hash
}
if ($hashes.Count -gt 0) {
    $sha256Content = ($hashes.GetEnumerator() | ForEach-Object { "$($_.Value)  $($_.Key)" }) -join "`n"
    Set-Content -Path (Join-Path $ReleasesRoot "SHA256SUMS") -Value $sha256Content -Encoding ASCII
    Write-Host "  [OK] SHA256SUMS" -ForegroundColor Green
}

Write-Host ""
Write-Host "Pacote pronto em:" -ForegroundColor Green
Write-Host "  $ReleasesRoot" -ForegroundColor White
Write-Host ""
Write-Host "Conteudo:" -ForegroundColor Cyan
Get-ChildItem -Path $ReleasesRoot | ForEach-Object {
    $size = if ($_.PSIsContainer) { "" } else { " ($([math]::Round($_.Length / 1KB, 0)) KB)" }
    Write-Host "  $($_.Name)$size"
}
Write-Host ""
Write-Host "Pra enviar pro usuario:" -ForegroundColor Cyan
Write-Host "  - Compacte a pasta inteira em ZIP, ou"
Write-Host "  - Mande apenas o .exe + COMO_INSTALAR.txt (mais simples)"
