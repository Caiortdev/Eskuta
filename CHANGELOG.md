# Changelog

Todas as mudanças notáveis nesse projeto ficam neste arquivo, seguindo
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
versionamento [SemVer](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Adicionado

- Atalhos de teclado globais: `Ctrl+H` (Home), `Ctrl+U` (Upload), `Ctrl+,` (Settings)
- Toggle de tema light/dark/system na sidebar (persistido em localStorage)
- Onboarding inteligente: pula automaticamente se ≥1 STT + ≥1 LLM já configurados
- Endpoint `GET /health/detailed` — checks granulares (DB, disco, keyring, dirs)
- Reaper de meetings travadas no startup do sidecar (timeout > 1h em status intermediário → marca como `failed`)
- Timeout global de 30min no pipeline `process_meeting`
- Pre-warm dos SDKs (groq/anthropic/openai/httpx) no startup do sidecar
- Backoff exponencial no polling de `/status` (1s→8s com jitter)
- Rate limiting global no sidecar (slowapi: 120/min, 30/s)
- CSP restritiva em `tauri.conf.json` (sem `unsafe-inline` em script-src)

### Mudado

- `pytest` 8.3.3 → 9.0.3 (fecha GHSA-6w46-j5rx-g56g)
- `pytest-asyncio` 0.24.0 → 1.3.0 (compat com pytest 9)

## [0.1.0] — 2026-05-22

Primeira release pública pré-lançamento. Implementa a **Fase 1 do MVP** descrita em [docs/RELATORIO_TECNICO.md](docs/RELATORIO_TECNICO.md).

### Adicionado

#### Pipeline de geração de ata

- Upload de áudio MP3/MP4/M4A/WAV até 500MB com hash streaming + path UUID (anti-traversal)
- Conversão de áudio via FFmpeg
- Voice Activity Detection (Silero VAD) com cache por audio_hash
- Chunking inteligente com snap-to-silence (alinhamento a pausas)
- Transcrição multi-provider (Groq Whisper primário + AssemblyAI fallback)
- Diarização opcional via pyannote.audio
- Geração de ata estruturada via LLM (Claude / GPT / Gemini)
- Anti-hallucination: JSON mode + Pydantic strict + evidence quotes + LLM-as-judge + fuzzy validator (rapidfuzz)
- Regeneração automática (até 2x) se validação falhar
- Persistência em SQLite com migrations Alembic bilíngues

#### Interface

- 5 telas: Onboarding, Home (lista), Upload, Processing (polling), MeetingDetail (3 tabs), Settings
- Modal `ApiKeyGuideModal` com instruções passo-a-passo por provider + suporte a hotspots
- Botão "Salvar e testar" — pré-valida API key antes de gravar no keyring
- Botão "Testar agora" pra revalidar key existente
- Componente `UpdateChecker` (notifica nova versão quando habilitado)

#### Endpoints REST (12 totais)

- `POST/GET /api/meetings`, `GET /api/meetings/{id}`, `GET /api/meetings/{id}/status`, `PUT /api/meetings/{id}/speaker-map`, `DELETE /api/meetings/{id}`
- `GET/PUT/DELETE/POST /api/keys` + `/test`
- `POST /api/transcription/start`
- `GET /api/diagnostics/export-logs`
- `GET /health`

#### Build & Distribuição

- Pipeline 4-etapas em `scripts/build.ps1` (PyInstaller sidecar → copy → vite → tauri MSI + NSIS)
- `build_sidecar.py` com hidden_imports cobrindo keyring backends + SDKs LLM/STT + alembic + libs de áudio
- `tauri.conf.json` com bundle MSI + NSIS bilíngue (pt-BR + en-US)
- Auto-update via `tauri-plugin-updater` com chave Ed25519 (active=false por default)
- `scripts/generate-update-keys.ps1` + `sign-release.ps1` pra workflow de assinatura
- Manifesto JSON de exemplo em `docs/example-update-manifest.json`

#### Observabilidade

- Loguru com rotação 50MB + retention 14d
- Masking robusto de API keys nos logs (regex pra Groq/Anthropic/OpenAI/Google/AssemblyAI + Bearer + JSON fields)
- Audit log no DB (configure/test/delete key, upload, delete meeting)
- Endpoint `/api/diagnostics/export-logs` retorna ZIP de logs masked + metadata

#### Segurança

- API keys nunca em disco (apenas keyring nativo do OS)
- Allow-list rígida de providers
- CORS restrito a localhost:1420 + tauri://localhost
- Streaming upload com chunks de 4MB + limite 500MB enforced
- UUID-based filename (sem path traversal)

#### Testes

- 550+ testes Python (95% coverage)
- 14 arquivos de teste frontend (≥70% coverage por gate)
- CI matrix: lint, format, typecheck, test, audit, Rust fmt+clippy, Tauri smoke build Windows
- Pre-commit hooks: ruff, prettier, eslint, cargo fmt, EOL, trailing whitespace

#### Documentação

- `docs/MAPA_PROJETO.md`, `RELATORIO_TECNICO.md`, `SCHEMA_BD.xlsx`
- 9 audit docs por fase (`AUDIT-FASE-{0..1.11+1.12}.md`)
- `BUILD-DISTRIBUTION.md`, `AUTO-UPDATE.md`, `RELEASE-READINESS.md`
- `CONTRIBUTING.md` pra contribuidores

### Conhecido (gaps documentados)

- Screenshots dos consoles dos providers ainda não capturados — modal funciona graciosamente sem (`onError` esconde img quebrada)
- Auto-update `active=false` por default (exige servidor de updates + chave Ed25519 gerada)
- Sem code signing (Windows SmartScreen mostra warning)
- macOS/Linux builds não automatizados no CI
- Validação do build em VM Windows limpa pendente

Detalhes em [docs/RELEASE-READINESS.md](docs/RELEASE-READINESS.md).

---

[Unreleased]: https://github.com/Caiortdev/Eskuta/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Caiortdev/Eskuta/releases/tag/v0.1.0
