# Eskuta — Release Readiness Report

**Data:** 2026-05-22
**Versão analisada:** 0.1.0 (fim da Fase 1 do RELATORIO_TECNICO)
**Branch:** `phase-1.11-1.12-final`
**Escopo:** MVP — upload de áudio → transcrição → ata estruturada (PT-BR)

---

## TL;DR — Nota geral: **7.6 / 10**

O Eskuta está **tecnicamente pronto pra beta privado** (~10-30 usuários
de confiança) mas tem **3 gaps importantes pra release pública**:

1. **Sem code signing** — Windows SmartScreen vai assustar usuários novos
2. **Sem servidor de updates ativo** — plugin instalado e desabilitado por default
3. **Screenshots do guia de API key ainda não capturados** — modal funciona, mas com fallback textual

Tudo o resto (pipeline, segurança, testes, observabilidade) está em
**bom estado para o estágio do projeto**.

| Área | Nota | Resumo |
|------|------|--------|
| Segurança | 8.5 | Forte: keyring, masking, allow-list de providers, CORS restrito. Gap: sem code signing. |
| Performance | 7.5 | Bundle compacto, cache VAD, snap-to-silence. Gap: polling agressivo 2s no Processing. |
| UX | 7.0 | Onboarding, fluxos cobertos. Gap: sem screenshots reais, modal só com texto. |
| Testes & QA | 9.0 | 550 tests Python + 14 arquivos frontend, 95% cov backend, 73% cov frontend. Suite robusta. |
| Distribuição | 6.5 | Build pipeline pronto. Gap: sem servidor updates, sem code signing, só Windows. |
| Observabilidade | 8.0 | Loguru com masking, export ZIP, audit_log. Gap: sem error tracking centralizado (Sentry). |
| Documentação | 8.5 | RELATORIO, BUILD, AUTO-UPDATE, AUDIT por fase. Gap: docs do usuário final. |
| Robustez | 7.5 | Fallback STT, retry exponential, evidence quotes. Gap: sem rate limiting no sidecar. |

---

## Métricas do projeto

| Métrica | Valor |
|---------|-------|
| **LoC frontend (src/)** | 4.462 |
| **LoC backend (src-python/app/)** | 6.583 |
| **LoC wrapper (src-tauri/src/)** | 106 |
| **Tests backend** | 550 passing |
| **Test files frontend** | 14 |
| **Coverage backend** | 95% (gate: 70%) |
| **Coverage frontend** | 73% (gate: 70%) |
| **Endpoints REST** | 12 |
| **Bundle frontend (raw)** | 400 kB |
| **Bundle frontend (gzip)** | 120 kB |
| **Vulnerabilidades runtime** | 0 (`pip-audit -r requirements.txt`) |
| **Vulnerabilidades npm** | 0 (`npm audit`) |
| **Vulnerabilidades dev-only** | 4 (pytest 8.3.3, setuptools 65.5.0) — fora do bundle |

---

## 1. Segurança — **8.5 / 10**

### ✅ Pontos fortes

- **API keys no keyring nativo do OS** (Credential Manager no Windows,
  Keychain no macOS). Nunca em arquivo. Implementado em `src-python/app/services/keys.py`.
- **Allow-list rígida de providers** (`KNOWN_PROVIDERS`): qualquer
  provider não-conhecido retorna 404. Defesa contra path traversal /
  parameter injection.
- **CORS restrito ao localhost do Tauri** (`http://localhost:1420`,
  `tauri://localhost`) — sem `*`. Definido em `src-python/app/main.py`.
- **Masking robusto de keys em logs** (`src-python/app/services/log_masking.py`):
  regex para Groq (`gsk_`), Anthropic (`sk-ant-`), OpenAI (`sk-proj-`,
  `sk-`), Google (`AIza`), AssemblyAI (32-hex), Bearer headers,
  campos JSON `api_key`/`token`/`password`/`secret`.
- **Streaming hash em upload** + limite 500MB enforced + UUID-based
  filename (sem path traversal).
- **Audit log** de toda operação sensível (configure/delete/test key,
  upload, delete meeting). Sem incluir valores das keys.
- **Endpoint sidecar bind em 127.0.0.1** (não 0.0.0.0). Outros
  processos do mesmo Windows podem conectar — mas não a rede.
- **JSON mode + Pydantic strict** nos LLMs (evita prompt injection
  via reunião).

### ⚠ Gaps

- **Sem code signing** do MSI/NSIS (decisão consciente — custo ~US$ 200/ano
  certificado EV). Resultado: SmartScreen do Windows mostra warning
  na primeira execução. Documentado em `docs/BUILD-DISTRIBUTION.md`.
- **Sem rate limiting** no sidecar — se algum app malicioso local
  descobrir a porta, pode disparar uploads/transcrições infinitas
  consumindo crédito do usuário. Mitigador: localhost-only +
  validação de filename.
- **Dev deps vulneráveis** (pytest 8.3.3 → 9.0.3, setuptools 65.5.0 → 78.1.1).
  **Fora do bundle de produção** — só afetam contribuidores. Recomendo
  bump em PR separado.
- **CSP do Tauri `null`** (em `tauri.conf.json`). Tauri 2 já mitiga
  XSS via webview isolation, mas configurar CSP estrita seria
  defense-in-depth.

### Recomendações
1. Bumpar pytest pra 9.0.3+ em PR separado (low risk)
2. Adicionar CSP restritiva em tauri.conf.json antes do release público
3. Avaliar code signing (US$ 200/ano EV cert) quando publicar pra > 100 users

---

## 2. Performance — **7.5 / 10**

### ✅ Pontos fortes

- **Bundle frontend pequeno** (120kB gzip) — webview carrega em <500ms.
- **Cache VAD por arquivo** (`src-python/app/services/audio/vad_cache.py`)
  — reprocesso de mesmo áudio é O(1) na fase 1 do pipeline.
- **Snap-to-silence em chunking** (fase 1.9.5) — chunks alinhados a
  silêncios, melhor qualidade da STT e menos custo de tokens.
- **Async I/O em todo o sidecar** (aiosqlite, httpx, AsyncAnthropic,
  AsyncGroq). Sem bloqueio em chamadas long-running.
- **PyInstaller --onefile** — startup do sidecar ~3-5s primeira vez
  (extração temp), <1s execuções seguintes.
- **Streaming upload com chunks 4MB** — não estoura memória mesmo em
  arquivos de 500MB.

### ⚠ Gaps

- **Polling de status a 2s** (`ProcessingPage` → `/status`) é
  agressivo pra reuniões longas (50min @ 2s = 1500 req). Considerar
  backoff exponencial ou WebSocket/SSE.
- **Sem pré-aquecimento dos SDKs** — primeira chamada de Groq/Anthropic
  paga o costo de import + TLS handshake.
- **Sem cache de transcript** — se usuário reprocessa, baixa tudo de
  novo da Groq/AssemblyAI.

### Recomendações
1. Trocar polling por SSE (FastAPI suporta nativamente)
2. Pre-warm clients no startup do sidecar
3. Cache de transcript por audio_hash (fácil, reusa estrutura do VAD cache)

---

## 3. UX — **7.0 / 10**

### ✅ Pontos fortes

- **Onboarding dedicado** (`/onboarding`) na primeira execução
- **5 telas fluem bem**: Home → Upload → Processing → MeetingDetail → Settings
- **Estados de loading + erro tipados** em todas as páginas (kind: "starting" | "ready" | "failed")
- **EvidenceQuote inline** na ata — toda decisão/ação tem o trecho da reunião
  que sustentou (anti-alucinação)
- **Botão "Como obter minha chave"** com modal passo-a-passo por provider
- **"Salvar e testar"** pré-valida key antes de gravar no keyring
- **Feedback visual** após teste (latência + status + http_status)
- **Acessibilidade básica**: role="dialog", aria-modal, aria-label,
  focus management no modal, Esc fecha
- **Português 100%** — labels, mensagens, datas (Intl.DateTimeFormat 'pt-BR')

### ⚠ Gaps

- **Sem screenshots reais** no ApiKeyGuideModal — o componente está
  pronto pra exibir, mas as imagens dos 5 consoles (`public/api-key-guides/{provider}/*.png`)
  ainda não foram capturadas (depende de coordenar com user + Chrome MCP).
- **Sem dark mode toggle** (variáveis CSS existem mas sem switcher).
- **Sem keyboard shortcuts** (ex: Ctrl+U para upload, Ctrl+, para settings).
- **Mensagens de erro genéricas** em alguns paths (ex: "boom interno"
  do backend → expor melhor).
- **Onboarding é estático** — não detecta se o usuário já configurou
  alguma key e pula automaticamente.

### Recomendações
1. **Capturar screenshots** via Chrome MCP (tarefa #18 — bloqueada por extensão Chrome)
2. Adicionar shortcut Cmd/Ctrl+, → Settings
3. Onboarding inteligente — pula direto pra Home se há ≥1 key configurada

---

## 4. Testes & QA — **9.0 / 10**

### ✅ Pontos fortes

- **550 tests passing** em backend, **95% coverage** (gate 70%)
- **97 tests frontend** com 73% branch coverage (gate 70%)
- **Tests por área**:
  - DB models + migrations (test_models, test_migrations)
  - Audio pipeline (test_audio_chunker, vad, converter)
  - Providers de STT (groq, assemblyai) com mock + fallback
  - Providers de LLM (claude, gpt, gemini) com mock JSON mode
  - Anti-hallucination (judge prompt, fuzzy validator)
  - Pipeline orquestração end-to-end
  - API keys + key validator (mock dos SDKs)
  - Logs masking (todos os 5 providers + Bearer + JSON fields)
  - Diagnostics export (assert que keys não vazam no ZIP)
- **Fixtures isoladas**: in_memory_keyring, isolated_app_dir, loguru_messages
- **CI matrix completa**: lint, format, typecheck, test, audit,
  Rust fmt+clippy, Tauri smoke build (Windows)
- **Coverage exclui types puros** + Shadcn copy (corretamente)
- **Pre-commit hooks**: ruff, prettier, eslint, cargo fmt, trim
  whitespace, EOL fix

### ⚠ Gaps

- **Sem testes E2E** (Playwright/Cypress contra app real)
- **Sem testes de smoke do binário empacotado** (PyInstaller pode
  quebrar import dinâmico que tests não pegam)
- **Sem benchmark de regressão** continuo (existe `evaluation/` mas
  não roda em CI)
- **Tauri Rust com 1 teste só** (smoke do greet) — lib.rs com 106 LoC
  basicamente sem cov

### Recomendações
1. Adicionar 1 E2E "happy path" (upload → ata renderizada)
2. Smoke test do `eskuta-sidecar.exe` empacotado em CI (rodar `--health` + curl)
3. CI: rodar `evaluation/` em PRs que mexem em pipeline

---

## 5. Distribuição — **6.5 / 10**

### ✅ Pontos fortes

- **Build pipeline unificado** (`scripts/build.ps1`) em 4 etapas
- **PyInstaller bundle do sidecar** com hidden_imports cobrindo
  keyring/uvicorn/SQLAlchemy/SDKs LLM
- **MSI + NSIS bilíngue** (pt-BR + en-US) configurado
- **Auto-update integrado** (`tauri-plugin-updater`) — scripts pra
  gerar chave Ed25519, assinar release, gerar manifesto JSON
- **Documentação completa de build** (`docs/BUILD-DISTRIBUTION.md`)
  e auto-update (`docs/AUTO-UPDATE.md`)

### ⚠ Gaps

- **Auto-update DESABILITADO por default** (`active: false`) — precisa
  flipar pra true E configurar endpoint real (servidor não existe)
- **Sem certificado de code signing** — SmartScreen warning na
  primeira execução
- **Só Windows automatizado** — macOS/Linux suportados pelo Tauri
  mas sem CI matrix
- **Sem CI workflow de release** (tag → build assinado → GitHub
  Releases) — só documentação do que viria
- **Bundle MSI ainda não testado em máquina limpa** — script pronto
  mas validação em VM limpa ainda não foi feita

### Recomendações
1. Validar `pwsh scripts/build.ps1` em VM Windows limpa antes do
   primeiro release público
2. Subir servidor de updates (Cloudflare R2 + Worker) — ~US$ 0/mês
3. Workflow de release em GitHub Actions (workflow exemplo está em
   `docs/AUTO-UPDATE.md`)
4. Avaliar Apple Developer ID + EV cert quando passar de ~100 users

---

## 6. Observabilidade — **8.0 / 10**

### ✅ Pontos fortes

- **Loguru com rotação** (50MB/14d) + intercept do stdlib logging
- **Logs estruturados** com kwargs (`logger.info("msg", provider="groq",
  latency_ms=42)`)
- **Masking automático** em export — keys nunca vazam pro ZIP de suporte
- **Export ZIP via endpoint REST** (`/api/diagnostics/export-logs`)
  com metadata sobre app version, OS, Python, providers configurados
- **Audit log no DB** — toda ação sensível com timestamp
- **CommandEvent capturado** do sidecar pelo Tauri (stdout/stderr
  printados no console do app)

### ⚠ Gaps

- **Sem error tracking centralizado** (Sentry/Rollbar/Bugsnag) — erros
  ficam só nos logs locais. Pra release pública, ter telemetria opt-in
  acelera muito o debug.
- **Sem métricas de uso** — não dá pra saber se 80% dos usuários
  travam no upload ou na Settings.
- **Logs do Tauri (Rust)** não vão pro mesmo arquivo do Python.
  Suporte precisa de 2 lugares pra olhar.

### Recomendações
1. Avaliar Sentry com opt-in explícito no onboarding (telemetry on/off)
2. Unificar logging Tauri → arquivo do loguru via custom appender Rust
3. Adicionar prometheus-like counters no sidecar (uploads, transcrições, erros)

---

## 7. Documentação — **8.5 / 10**

### ✅ Pontos fortes

- **`MAPA_PROJETO.md`** — visão geral do projeto
- **`RELATORIO_TECNICO.md`** — roadmap completo com etapas, código,
  critérios de aceite
- **`SCHEMA_BD.xlsx`** — esquema do banco
- **`AUDIT-FASE-{0..1.10}.md`** — auditoria de segurança/integridade
  por fase (9 docs)
- **`BUILD-DISTRIBUTION.md`** + **`AUTO-UPDATE.md`** (este PR)
- **`MELHORIAS-CONCORRENTE.md`** — análise comparativa
- **`CONTRIBUTING.md`** — onboarding pra contribuidores
- **Docstrings extensivas** em todos os módulos Python
- **Tipos explícitos** em TypeScript (sem `any` informal)

### ⚠ Gaps

- **Sem README do usuário final** — quem clona o repo vê README do
  Tauri default
- **Sem changelog** (`CHANGELOG.md`) — comum em apps com auto-update
- **Sem screenshots no README** mostrando o app rodando
- **Sem demo video/GIF**

### Recomendações
1. **Reescrever `README.md`** focado no usuário (não dev): print screen,
   "como instalar", "como obter API keys", link pro release
2. Adicionar `CHANGELOG.md` antes do primeiro release (vai virar release
   notes no auto-update)
3. Gravar 2-3min de demo (Loom/Camtasia) — pode ir no README

---

## 8. Robustez & Confiabilidade — **7.5 / 10**

### ✅ Pontos fortes

- **Fallback automático Groq → AssemblyAI** se Groq falhar
- **Retry com exponential backoff** nos providers LLM
- **JSON mode + Pydantic strict** rejeita output mal formado do LLM
- **Anti-hallucination judge** valida que `quote` aparece na transcrição
- **Idempotent delete** (soft delete + 204 mesmo em re-delete)
- **DB com migrations Alembic** — schema versionado, reversível
- **SQLite WAL mode** pra melhor concorrência

### ⚠ Gaps

- **Sem health check granular** — `/health` retorna ok mas não checa
  DB writable, keyring acessível, disco com espaço
- **Sem timeout global no pipeline** — reunião patologica pode rodar
  indefinidamente
- **Sem dead-letter** pra meetings que falham no pipeline (ficam em
  `failed` mas sem retry automatizado)
- **Sem proteção contra encerramento abrupto** do sidecar (kill -9)
  durante processing — pode deixar meeting em status intermediário

### Recomendações
1. `/health/detailed` que verifica DB + disco + keyring
2. Timeout global no `process_meeting` (ex: 30min hard limit)
3. Job de "reaper" no startup que marca meetings em status intermediário
   como `failed` (não ficam para sempre em "transcribing")

---

## Roadmap pra release pública (post-fase 1)

| Prioridade | Item | Esforço |
|------------|------|---------|
| 🔴 P0 | Capturar screenshots dos 5 consoles (Chrome MCP) | 2h |
| 🔴 P0 | Validar build em VM Windows limpa | 4h |
| 🔴 P0 | Reescrever README.md (usuário final) | 3h |
| 🟡 P1 | Subir servidor de updates (Cloudflare R2 + Worker) | 1d |
| 🟡 P1 | Configurar Sentry com opt-in | 4h |
| 🟡 P1 | Adicionar CHANGELOG.md + workflow de release | 4h |
| 🟢 P2 | Bumpar pytest 9.0.3 (dev deps) | 1h |
| 🟢 P2 | CSP restritiva em tauri.conf.json | 2h |
| 🟢 P2 | E2E happy path (Playwright) | 6h |
| 🟢 P2 | `/health/detailed` + timeout global pipeline | 4h |
| 🔵 P3 | Code signing (EV cert) | 1d + US$ 200/ano |
| 🔵 P3 | macOS/Linux build matrix | 2d |
| 🔵 P3 | Auto-update ATIVO (depende de servidor) | 4h (depois do servidor) |

**Total P0:** ~9 horas → pode lançar beta privado nesta semana.
**Total P0+P1:** ~3 dias → ready para release pública controlada.

---

## Conclusão

O Eskuta na Fase 1 está em **estado significativamente acima da média
para um MVP open-source**: cobertura de testes acima do gate, audit log
funcional, masking robusto, build pipeline pronto, pipeline anti-
hallucination implementado.

Os gaps que restam são **operacionais (subir servidor de update,
capturar screenshots, validar build)** e **de polish (README usuário,
CSP, error tracking)** — nenhum é técnico/arquitetural.

**Recomendação:** lançar **beta privado** pra ~10 usuários de
confiança imediatamente, e usar feedback deles pra priorizar entre
P1/P2 antes do release público.

---

*Relatório gerado durante a Fase 1.11+1.12 do projeto. Próxima revisão
sugerida após a Fase 2 (captura em tempo real).*
