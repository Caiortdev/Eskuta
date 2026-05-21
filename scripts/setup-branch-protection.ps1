<#
.SYNOPSIS
    Configura branch protection rules na branch `main` do repo Eskuta.

.DESCRIPTION
    Aplica via `gh api` as regras que garantem que nada entra em main sem:
      - Todos os jobs do CI verde (status checks obrigatorios)
      - Pull request aprovado (configuravel, ver -RequireReviews)
      - Conversations resolvidas
      - Sem force-push
      - Sem deletion da branch

    E idempotente -- rodar de novo apenas reaplica a mesma config.

    Pre-requisito:
      - `gh` autenticado como usuario com admin no repo

.PARAMETER RequireReviews
    Numero de aprovacoes de PR exigidas. 0 = solo-friendly (so status
    checks bloqueiam merge). 1+ = exige review humano. Default: 0.

.PARAMETER Owner
    Owner do repo (default: Caiortdev).

.PARAMETER Repo
    Nome do repo (default: Eskuta).

.EXAMPLE
    pwsh scripts/setup-branch-protection.ps1
    pwsh scripts/setup-branch-protection.ps1 -RequireReviews 1
#>

[CmdletBinding()]
param(
    [int] $RequireReviews = 0,
    [string] $Owner = 'Caiortdev',
    [string] $Repo = 'Eskuta',
    [string] $Branch = 'main'
)

$ErrorActionPreference = 'Stop'

# Status checks que TODO PR pra main precisa ter verde. Tem que bater
# exatamente com o `name:` declarado no .github/workflows/ci.yml.
$requiredChecks = @(
    'Sidecar Python (lint + test)',
    'Frontend (typecheck + test)',
    'Frontend (lint + format)',
    'Rust (fmt + clippy)',
    'Auditoria (npm audit + pip-audit)',
    'Pre-commit hooks (sanity)',
    'Tauri build (Windows, smoke)'
)

# Reviews
$prReviews = if ($RequireReviews -gt 0) {
    @{
        required_approving_review_count = $RequireReviews
        dismiss_stale_reviews            = $true
        require_code_owner_reviews       = $false
        require_last_push_approval       = $true
    }
}
else {
    # Solo-friendly: so status checks bloqueiam (sem aprovacao humana
    # obrigatoria), mas o owner ainda precisa criar um PR (nao pode
    # pushar direto em main).
    $null
}

$payload = @{
    required_status_checks           = @{
        strict   = $true # branch tem que estar up-to-date com main antes do merge
        contexts = $requiredChecks
    }
    enforce_admins                   = $false # owner pode bypassar em emergencia
    required_pull_request_reviews    = $prReviews
    restrictions                     = $null
    allow_force_pushes               = $false
    allow_deletions                  = $false
    required_conversation_resolution = $true
    required_linear_history          = $false # permitimos merge commits e rebase
    block_creations                  = $false
}

$payloadJson = $payload | ConvertTo-Json -Depth 10 -Compress
# Escreve sem BOM -- gh CLI rejeita JSON com BOM (HTTP 400).
$payloadFile = New-TemporaryFile
[System.IO.File]::WriteAllText(
    $payloadFile.FullName,
    $payloadJson,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Aplicando branch protection em $Owner/$Repo `:$Branch" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Status checks obrigatorios:" -ForegroundColor Yellow
$requiredChecks | ForEach-Object { Write-Host "  * $_" }
Write-Host ""
if ($RequireReviews -gt 0) {
    Write-Host "Reviews obrigatorias: $RequireReviews (dismiss stale on push)" -ForegroundColor Yellow
}
else {
    Write-Host "Reviews obrigatorias: 0 (solo-friendly -- so status checks bloqueiam)" -ForegroundColor Yellow
}
Write-Host ""

gh api `
    --method PUT `
    -H "Accept: application/vnd.github+json" `
    "/repos/$Owner/$Repo/branches/$Branch/protection" `
    --input $payloadFile

Remove-Item $payloadFile -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "OK -- Branch protection aplicada." -ForegroundColor Green
Write-Host ""
Write-Host "Pra aumentar seguranca no futuro:" -ForegroundColor Yellow
Write-Host "  pwsh scripts/setup-branch-protection.ps1 -RequireReviews 1"
Write-Host ""
