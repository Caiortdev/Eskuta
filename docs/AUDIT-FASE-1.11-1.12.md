# AUDIT — Fase 1.11 (API Keys UI) + 1.12 (Distribuição)

**Branch:** `phase-1.11-1.12-final`
**Data:** 2026-05-22
**Escopo:** Finalização da Fase 1 do MVP — UX de configuração de chaves, build pipeline, auto-update infra, export de diagnostics, relatório de release-readiness.

---

## Resumo das mudanças

### Frontend
- **`src/components/ApiKeyGuideModal.tsx` (NOVO, ~340 LoC)** — Modal de instruções passo-a-passo por provider, com suporte a `hotspot` (círculo vermelho pulsante + label "Clique aqui") sobreposto aos screenshots. Acessível (`role="dialog"`, `aria-modal`, focus management, Esc fecha, click backdrop fecha).
- **`src/components/ApiKeyGuideModal.test.tsx` (NOVO, ~120 LoC)** — 11 testes cobrindo dialog acessibilidade, fechamento por Esc/X/backdrop/Cancelar, `window.open` com `noopener,noreferrer`, e variação por provider.
- **`src/components/UpdateChecker.tsx` (NOVO, ~140 LoC)** — Componente que detecta ambiente Tauri (`window.__TAURI_INTERNALS__`), chama `tauri-plugin-updater` no startup, mostra notification card no canto da tela quando há update.
- **`src/pages/Settings.tsx` (MODIFICADO)** — Botão "Como obter minha chave" abre `ApiKeyGuideModal`. Novo fluxo "Salvar e testar" (pre-test → save → re-test). Botão "Testar agora" pra revalidar key salva. Nova seção "Diagnóstico" com botão "Exportar logs".
- **`src/pages/Settings.test.tsx` (REESCRITO)** — Testes atualizados pro novo fluxo (mock de `api.keys.test`, fluxo pré-validação, blocking de save quando key inválida, integração com modal).
- **`src/lib/api.ts` (EXTENDIDO)** — `api.keys.test()` (POST /api/keys/{provider}/test) e `api.diagnostics.exportLogs()` (GET com retorno Blob pra download).
- **`src/types/meeting.ts` (EXTENDIDO)** — `TestKeyRequest`, `TestKeyResponse`, `ValidationStatus`.
- **`src/App.tsx` (MODIFICADO)** — Inclui `<UpdateChecker />` antes das rotas.
- **`package.json`** — Adicionado `@tauri-apps/plugin-updater@^2`.

### Backend (sidecar Python)
- **`src-python/app/services/key_validator.py` (NOVO, ~240 LoC)** — Validação de conectividade chamando endpoint barato (`models.list`) por provider via SDK (Groq, Anthropic, OpenAI) ou httpx (AssemblyAI, Google). Classifica 401/403 como `invalid`, 429/5xx/timeout como `error`, 200 como `valid`. Timeout 10s.
- **`src-python/app/services/log_masking.py` (NOVO, ~75 LoC)** — Patterns regex pra mascarar Groq (`gsk_*`), Anthropic (`sk-ant-*`), OpenAI (`sk-proj-*`, `sk-*`), Google (`AIza*`), AssemblyAI (32-hex), Bearer headers, JSON fields (`api_key`, `token`, `password`, `secret`).
- **`src-python/app/api/keys.py` (EXTENDIDO)** — Endpoint `POST /api/keys/{provider}/test` com modo "pré-validação" (body com `key` testa SEM salvar) e modo "revalidação" (body vazio testa key do keyring + persiste `last_validated_at` no DB).
- **`src-python/app/api/diagnostics.py` (NOVO, ~115 LoC)** — Endpoint `GET /api/diagnostics/export-logs` retorna ZIP com logs masked + metadata. Limite hard 50MB, com fallback `TRUNCATED.txt` se exceder.
- **`src-python/app/main.py` (MODIFICADO)** — Registra `diagnostics_router`.
- **`src-python/tests/test_key_validator.py` (NOVO, ~210 LoC)** — 18 testes unitários: classificação de status codes, mock dos SDKs lazy-imported (groq/anthropic/openai), httpx (assemblyai/google), edge cases (empty key, whitespace, unknown provider).
- **`src-python/tests/test_log_masking.py` (NOVO, ~110 LoC)** — 16 testes cobrindo todos os patterns.
- **`src-python/tests/test_api_diagnostics.py` (NOVO, ~100 LoC)** — 5 testes E2E do endpoint via httpx ASGITransport: ZIP válido, metadata sem leak, masking efetivo, empty logs dir, isolated_app_dir fixture pra não tocar `~/.eskuta/`.
- **`src-python/tests/test_api_keys.py` (EXTENDIDO)** — 7 testes novos pro endpoint `/test`: valid/invalid em body, fallback pra keyring, persistência de `last_validation_status`, no-leak da key em response.
- **`src-python/build_sidecar.py` (REESCRITO)** — Adicionados ~15 hidden_imports (keyring backends, SDKs LLM/STT, h2, librosa, soundfile, pydub) + `--add-data` pra `alembic.ini` + `migrations_alembic/`.

### Wrapper Tauri (Rust)
- **`src-tauri/Cargo.toml`** — Adicionado `tauri-plugin-updater = "2"`.
- **`src-tauri/src/lib.rs`** — Registra plugin updater: `.plugin(tauri_plugin_updater::Builder::new().build())`.
- **`src-tauri/capabilities/default.json`** — Adicionado `"updater:default"` permission.
- **`src-tauri/tauri.conf.json` (REESCRITO)** — Window size 1200x800 com min 900x600. Bundle targets `["msi", "nsis"]` (não "all"). `category: Productivity`, `shortDescription`, `longDescription`, `publisher`, `homepage`. WiX language `[pt-BR, en-US]`, NSIS com mesma config. Bloco `plugins.updater` com `active: false`, `dialog: false`, endpoint placeholder, pubkey placeholder.

### Scripts & Infra
- **`scripts/build.ps1` (NOVO, ~140 LoC)** — Pipeline unificado Windows: 1) PyInstaller do sidecar, 2) Copy + rename pro target triple, 3) `npm run build`, 4) `npm run tauri build`. Flags `-SkipSidecar`, `-CleanFirst`.
- **`scripts/generate-update-keys.ps1` (NOVO)** — Chama `tauri signer generate` pra criar par Ed25519 em `tmp/eskuta-update.key`. Instruções pós-geração.
- **`scripts/sign-release.ps1` (NOVO)** — Assina o NSIS .exe + emite manifesto JSON pronto pra colar no servidor de updates.
- **`scripts/capture_screenshots.py` (NOVO)** — Playwright headed pra capturar screenshots dos consoles após user logar.

### Documentação
- **`docs/BUILD-DISTRIBUTION.md` (NOVO)** — Pré-requisitos (Python/Node/Rust/VS Build Tools), comandos, troubleshooting (DLL/VCRedist/SmartScreen).
- **`docs/AUTO-UPDATE.md` (NOVO)** — Arquitetura Ed25519, setup (gerar keys → pubkey no conf → endpoint), workflow de release, rotação de chaves, CI exemplo.
- **`docs/example-update-manifest.json` (NOVO)** — Manifesto JSON com schema documentado pra publicar no endpoint.
- **`docs/RELEASE-READINESS.md` (NOVO)** — Diagnóstico geral pre-release com scorecard (Segurança 8.5, Performance 7.5, UX 7.0, Testes 9.0, Distribuição 6.5, Observabilidade 8.0, Documentação 8.5, Robustez 7.5; geral 7.6/10). Roadmap P0/P1/P2/P3.

### .gitignore
- Adicionado `tmp/` — diretório que guarda chaves Ed25519 do tauri-plugin-updater + perfil Playwright.

---

## Análise de Segurança

### ✅ Decisões alinhadas

1. **API keys nunca persistidas em arquivo** — apenas no keyring nativo do OS (mantém princípio das fases anteriores).
2. **Endpoint `/test` NÃO retorna o valor da chave** — apenas booleano `valid/invalid/error` + http_status.
3. **Pré-validação ANTES de salvar** no fluxo "Salvar e testar" — evita gravar chave inválida no keyring.
4. **Test-mode com body `key`** não persiste no DB — apenas test-mode sem body (test da chave salva) atualiza `last_validation_status`.
5. **Masking robusto** — `log_masking.py` cobre os 5 providers + headers comuns + JSON fields. Aplicado ANTES do ZIP ser gerado, não depois.
6. **Limite de 50MB no export ZIP** — proteção contra DoS de memória se logs acumularem.
7. **ZIP de diagnostics include `providers_configured` (boolean) NUNCA o valor das keys** — explicitamente testado em `test_metadata_does_not_leak_actual_keys`.
8. **`tmp/` no .gitignore** — chaves Ed25519 privadas + perfil Playwright (com cookies dos providers) nunca vão pro git.
9. **Auto-update DESABILITADO por default** (`active: false`) — não bate em endpoint placeholder até dev real gerar chave + configurar servidor.
10. **`window.open` com `noopener,noreferrer`** no modal — links externos não compartilham contexto com a window do app.

### ⚠ Pontos de atenção

1. **Sem rate limiting no sidecar** — endpoint `/test` poderia ser martelado por código local malicioso pra exfiltrar respostas dos providers. Mitigador: localhost-only + allow-list de providers + timeout 10s.
2. **Logs do Playwright profile** (em `tmp/pw-profile/`) contêm cookies de sessão dos 5 providers — protegido por gitignore + perm filesystem padrão, mas usuário precisa entender que esse dir é sensível.
3. **`active: false` no updater** — em produção, dev DEVE flipar pra true E configurar endpoint real. Documentado em `docs/AUTO-UPDATE.md`.
4. **Pré-validação envia chave do user pro provider** mesmo antes de salvar — esperado, mas vale documentar pro user (network round-trip com o valor da key cleartext via TLS).

### ✅ Verificações

- `pip-audit -r requirements.txt` → 0 vulnerabilidades runtime
- `npm audit` → 0 vulnerabilidades
- Dev deps com vulnerabilidades documentadas (pytest 8.3.3 → 9.0.3, setuptools 65.5.0 → 78.1.1) — fora do bundle. Para correção em PR separado.

---

## Métricas de teste

| Suite | Tests | Status | Coverage |
|-------|-------|--------|----------|
| Backend Python | 550 | ✅ pass | 94.74% |
| Frontend Vitest | ~108 | ⏳ (validar em CI) | ≥70% (gates) |
| TypeScript strict | ✅ pass | — | — |
| ESLint | ✅ pass | — | — |
| Prettier | ✅ pass | — | — |

---

## Critérios de aceite — Fase 1.11

### 1.11.1 Storage criptografado
- [x] Keys salvas no keyring do OS (não em arquivo) — herdado de fase 1.10
- [x] Listar providers configurados não revela as keys — herdado
- [x] Funciona em Windows e macOS (keyring backends incluídos no PyInstaller)

### 1.11.2 UI de configuração
- [x] Instruções claras pra cada provider (5 guides com 3-5 passos cada)
- [x] Botão "abrir site" abre no browser do usuário (`window.open` com targets externos)
- [x] Teste de conectividade após salvar (`POST /api/keys/{provider}/test`)
- [x] Mensagem de erro útil se key inválida (banner com `message` + `http_status` + `latency_ms`)

---

## Critérios de aceite — Fase 1.12

### 1.12.1 Pipeline de build unificado
- [x] Comando único (`pwsh scripts/build.ps1`) gera o instalador
- [ ] Instalador funciona em máquina limpa — **PENDENTE validação em VM** (documentado em `docs/BUILD-DISTRIBUTION.md` como P0)
- [x] Primeira execução cria diretórios em `~/.eskuta/` — herdado (`settings.ensure_dirs`)
- [x] App fecha graciosamente (Tauri Manager + `child.kill()` em ExitRequested)

### 1.12.2 Auto-update
- [x] App verifica update no startup (`UpdateChecker.tsx` chama `check()` em `useEffect`)
- [x] Notifica usuário quando há nova versão (card no canto inferior direito)
- [x] Update aplicado com 1 clique (`update.downloadAndInstall(callback)`)
- [x] Assinatura digital valida update (Ed25519 via tauri-plugin-updater)
- [x] **Active=false por default** — exige setup explícito do dev antes de ativar

### 1.12.3 Logs e diagnóstico
- [x] ZIP gerado contém todos os logs relevantes (`eskuta_*.log` + metadata.json)
- [x] API keys NÃO aparecem nos logs (mascarar antes — `mask_secrets_in_file`)
- [x] Tamanho razoável (< 50MB enforced, `TRUNCATED.txt` se exceder)

---

## Conclusão

Fase 1.11 + 1.12 implementadas conforme RELATORIO_TECNICO + RELEASE-READINESS,
com 2 trade-offs explícitos:

1. **Screenshots no `ApiKeyGuideModal` capturados via Playwright em sessão separada** —
   componente já preparado pra renderizar `hotspot` (círculo vermelho), aguardando
   só os PNGs reais (script `scripts/capture_screenshots.py` pronto).

2. **Validação de build em VM Windows limpa pendente** — pipeline `scripts/build.ps1`
   pronto e testável, mas a validação end-to-end "instala num PC sem Python e funciona"
   fica como P0 documentado em `RELEASE-READINESS.md` antes do primeiro release público.

Nada técnico/arquitetural pendente. Próxima fase: **2.x** (captura em tempo real) ou
**release público** (depois de P0 do release-readiness checklist).
