# Auto-update — Fluxo Ed25519 + tauri-plugin-updater

Este documento descreve como funciona o sistema de auto-update do Eskuta,
e o que você precisa fazer pra publicar uma nova versão que os usuários
recebem automaticamente.

> **Status atual:** O plugin está **integrado mas DESABILITADO** por
> default. Em `tauri.conf.json` → `plugins.updater.active=false`. Pra
> ativar você precisa: 1) gerar par de chaves, 2) subir endpoint de
> manifesto, 3) flipar pra true.

---

## Arquitetura

```
┌─────────────────┐                       ┌────────────────────────┐
│ App do usuário  │                       │ Servidor de updates    │
│ (instalado)     │   GET /target/        │ (Cloudflare R2 /       │
│                 │ ──── arch/current ──▶ │  S3 / GitHub Releases) │
│                 │                       │                        │
│                 │   200 + manifesto     │ Hospeda:               │
│                 │ ◀──── JSON ────────── │  - manifesto.json      │
│                 │                       │  - Eskuta_X.Y.Z.exe    │
│                 │                       │  - .exe.sig            │
│                 │   GET .exe + .sig     │                        │
│                 │ ─────────────────────▶│                        │
│                 │                       │                        │
│ verifica sig    │                       │                        │
│ instala         │                       │                        │
└─────────────────┘                       └────────────────────────┘
```

**Confiança:** cliente verifica a assinatura Ed25519 do binário com a
chave pública embutida no app (em `tauri.conf.json`). Se a assinatura
não bater com a chave pública, o update é rejeitado — não importa quem
controle o servidor.

---

## Setup inicial (uma vez por projeto)

### 1. Gerar par de chaves Ed25519

```powershell
pwsh scripts/generate-update-keys.ps1
```

Isso cria `tmp/eskuta-update.key` (privada) + `tmp/eskuta-update.key.pub`
(pública). A senha que você digita protege a chave privada.

### 2. Publicar a chave pública

Cole o conteúdo de `tmp/eskuta-update.key.pub` em `src-tauri/tauri.conf.json`:

```json
"plugins": {
  "updater": {
    "active": true,
    "dialog": false,
    "endpoints": [
      "https://seu-dominio.com/eskuta/updates/{{target}}/{{arch}}/{{current_version}}"
    ],
    "pubkey": "dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IDEyM0FCQwpSV1QrLi4u"
  }
}
```

**O pubkey vai pro git** — é projetado pra ser público. **A chave privada
NUNCA vai pro git.**

### 3. Guardar a chave privada com segurança

- **Backup local:** 1Password / Bitwarden / similar
- **CI/CD:** Adicionar como GitHub Actions secret:
  - `TAURI_PRIVATE_KEY` — conteúdo do arquivo `.key`
  - `TAURI_KEY_PASSWORD` — a senha que você digitou
- Apague `tmp/eskuta-update.key` do disco local quando subir pra senha manager

### 4. Configurar o servidor de updates

Você precisa de um endpoint HTTPS que responde com manifesto JSON.
Opções:

#### Opção A: Cloudflare R2 + Workers (recomendado)
- R2 hospeda os binários (.exe, .sig)
- Cloudflare Worker serve o manifesto JSON com lógica de versão
- ~US$ 0 pra projeto pequeno

#### Opção B: GitHub Releases + nginx redirector
- GitHub Releases hospeda os binários
- Um servidor mínimo serve o manifesto pegando da latest release

#### Opção C: S3 estático
- Manifesto JSON parado no S3
- Sem lógica de "última versão" — você precisa atualizar manualmente

### 5. Ativar o updater

Edite `src-tauri/tauri.conf.json`:

```json
"plugins": {
  "updater": {
    "active": true,    // <─── true
    ...
```

Build e teste:

```powershell
pwsh scripts/build.ps1
# Instale o build resultante
# Abra o app — UpdateChecker.tsx vai checar updates no startup
```

---

## Publicando uma nova release

A cada release nova:

### 1. Bump da versão

Atualize **em 3 lugares** (precisa bater):

- `package.json` → `"version"`
- `src-tauri/Cargo.toml` → `[package] version`
- `src-tauri/tauri.conf.json` → `"version"`

### 2. Build assinado

```powershell
# TAURI_PRIVATE_KEY e TAURI_KEY_PASSWORD precisam estar setados como env vars
$env:TAURI_PRIVATE_KEY = Get-Content ./tmp/eskuta-update.key -Raw
$env:TAURI_KEY_PASSWORD = "sua-senha-aqui"

pwsh scripts/build.ps1
```

Quando essas env vars estão setadas, o Tauri **automaticamente gera o
`.sig`** ao lado do `.exe` no `target/release/bundle/nsis/`.

### 3. (Opcional) Re-assinar manualmente

Se você só precisa re-gerar a assinatura sem rebuildar:

```powershell
pwsh scripts/sign-release.ps1 -Version "0.1.1" -PrivateKeyPath ./tmp/eskuta-update.key -ReleaseNotes "Fix do bug X"
```

Isso emite o manifesto JSON pronto pra colar no servidor.

### 4. Upload pro servidor

Suba **2 arquivos** pro seu servidor:

```
src-tauri/target/release/bundle/nsis/Eskuta_0.1.1_x64-setup.exe
src-tauri/target/release/bundle/nsis/Eskuta_0.1.1_x64-setup.exe.sig
```

### 5. Atualize o manifesto

O endpoint configurado em `tauri.conf.json` precisa servir um JSON
nesse formato:

```json
{
  "version": "0.1.1",
  "notes": "- Fix do bug X\n- Adiciona feature Y",
  "pub_date": "2026-06-15T10:30:00Z",
  "platforms": {
    "windows-x86_64": {
      "signature": "dW50cnVzdGVkIGNvbW1lbnQ6IHNpZ25hdHVyZSBmcm9tIHRhdXJpIHNlY3JldCBrZXkKUlVU...",
      "url": "https://seu-dominio.com/releases/v0.1.1/Eskuta_0.1.1_x64-setup.exe"
    }
  }
}
```

**Campos obrigatórios:**
- `version` — semver
- `platforms.{target}.signature` — conteúdo do `.sig` (string base64)
- `platforms.{target}.url` — URL absoluta do `.exe`

**Campos opcionais:**
- `notes` — release notes (markdown simples)
- `pub_date` — ISO 8601 UTC

### 6. Validar

- Instale a versão anterior em uma máquina limpa
- Abra o app
- `UpdateChecker.tsx` deve detectar update e mostrar notificação no canto
- Clique em "Instalar agora" → download → instala → "Reinicie pra aplicar"

---

## Rotação de chaves

**Se a chave privada vazar:** geração de nova chave **quebra o update
chain pros usuários antigos** (eles precisam reinstalar manualmente).
Por isso a chave privada é o ativo mais crítico do projeto.

Plano de rotação (em emergência):

1. Gerar novo par de chaves: `pwsh scripts/generate-update-keys.ps1`
2. Lançar uma nova versão com a nova pubkey em `tauri.conf.json`
3. **A nova versão precisa ser instalada manualmente** — os clientes antigos não vão aceitar a assinatura nova
4. Avisar usuários por outro canal (email, site) que precisam reinstalar
5. Revogar a chave antiga em todo lugar (GitHub secrets, password manager)

---

## CI/CD: workflow de release

Quando você decidir automatizar releases via GitHub Actions, o workflow
fica algo assim (exemplo conceitual — não está commitado ainda):

```yaml
name: release

on:
  push:
    tags: ["v*"]

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: dtolnay/rust-toolchain@stable
      - run: |
          cd src-python
          python -m venv venv
          .\venv\Scripts\activate
          pip install -r requirements.txt -r requirements-build.txt
      - run: npm ci
      - run: pwsh scripts/build.ps1
        env:
          TAURI_PRIVATE_KEY: ${{ secrets.TAURI_PRIVATE_KEY }}
          TAURI_KEY_PASSWORD: ${{ secrets.TAURI_KEY_PASSWORD }}
      - uses: softprops/action-gh-release@v2
        with:
          files: |
            src-tauri/target/release/bundle/nsis/*.exe
            src-tauri/target/release/bundle/nsis/*.sig
            src-tauri/target/release/bundle/msi/*.msi
```

---

## Manifesto de exemplo (referência)

Em `docs/example-update-manifest.json` tem um exemplo pronto pra você
servir do seu endpoint.
